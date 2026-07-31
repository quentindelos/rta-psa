"""Appels Vertex AI (Gemini) : embedding de requête, synthèse de réponse à partir de la
RTA, et réponse de secours sourcée via recherche web quand la RTA ne couvre pas le sujet."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
from google import genai
from google.genai import types

from .config import Settings
from .index_store import PageEntry

_ANSWER_PROMPT = """Tu réponds en français à une question sur une revue technique \
automobile (Peugeot 106 / Citroën Saxo), à partir UNIQUEMENT des extraits de pages \
fournis ci-dessous.

Réponds UNIQUEMENT avec un objet JSON valide (pas de balises markdown), avec exactement \
ces clés :
- "found_in_rta" : true si les extraits fournis permettent réellement de répondre à la \
question posée, false si ce n'est pas le cas (sujet non couvert, extraits hors sujet, \
véhicule différent, etc.). Ne mets pas true juste parce que les extraits parlent du même \
thème général — il faut qu'ils répondent vraiment à la question.
- "answer" : si found_in_rta est true, la réponse à la question, concise et directe, en \
citant systématiquement le(s) numéro(s) de page utilisé(s) (ex : "(page 42)"). Si \
found_in_rta est false, une chaîne vide "".
- "cited_pages" : si found_in_rta est true, la liste des numéros de page (parmi ceux des \
extraits fournis) RÉELLEMENT utilisés pour construire la réponse — uniquement celles qui \
contiennent l'information demandée, pas toutes les pages fournies. Liste vide sinon.

Question : {query}

Extraits disponibles :
{context}
"""

_WEB_ANSWER_PROMPT = """Tu es un assistant spécialisé sur l'entretien et la réparation \
des Peugeot 106, Citroën Saxo, Peugeot 205, Peugeot 206 et Peugeot 306. La revue \
technique officielle disponible ne couvre pas cette question. Réponds en français à \
partir d'une recherche web réelle, en t'appuyant sur des sources fiables (forums \
automobiles reconnus, documentation constructeur, sites de pièces détachées). Si tu \
n'es pas sûr, dis-le clairement plutôt que d'inventer une réponse.

Question : {query}
"""


@dataclass(frozen=True)
class WebSourceInfo:
    title: str
    url: str


@dataclass(frozen=True)
class RtaAnswer:
    found: bool
    answer: str
    cited_pages: list[str] = field(default_factory=list)


def _client(settings: Settings) -> genai.Client:
    return genai.Client(
        vertexai=True,
        project=settings.google_cloud_project,
        location=settings.google_cloud_region,
    )


def embed_query(settings: Settings, text: str) -> np.ndarray:
    client = _client(settings)
    response = client.models.embed_content(
        model=settings.embedding_model,
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    vector = np.array(response.embeddings[0].values, dtype=np.float32)
    norm = np.linalg.norm(vector)
    return vector / norm if norm > 0 else vector


def generate_answer(settings: Settings, query: str, pages: list[PageEntry]) -> RtaAnswer:
    client = _client(settings)
    context = "\n\n".join(f"--- Page {p.page_label} ---\n{p.text}" for p in pages)
    prompt = _ANSWER_PROMPT.format(query=query, context=context)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    try:
        data = json.loads(response.text or "{}")
    except json.JSONDecodeError:
        return RtaAnswer(found=False, answer="")
    cited_pages = [str(p) for p in (data.get("cited_pages") or [])]
    return RtaAnswer(
        found=bool(data.get("found_in_rta", False)),
        answer=data.get("answer", "") or "",
        cited_pages=cited_pages,
    )


def generate_web_answer(settings: Settings, query: str) -> tuple[str, list[WebSourceInfo]]:
    client = _client(settings)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=_WEB_ANSWER_PROMPT.format(query=query),
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
    )
    answer = response.text or ""

    sources: list[WebSourceInfo] = []
    seen_urls: set[str] = set()
    candidates = response.candidates or []
    grounding = getattr(candidates[0], "grounding_metadata", None) if candidates else None
    chunks = getattr(grounding, "grounding_chunks", None) or []
    for chunk in chunks:
        web = getattr(chunk, "web", None)
        if web and web.uri and web.uri not in seen_urls:
            seen_urls.add(web.uri)
            sources.append(WebSourceInfo(title=web.title or web.domain or web.uri, url=web.uri))

    return answer, sources
