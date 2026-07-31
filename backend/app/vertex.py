"""Appels Vertex AI (Gemini) : embedding de requête et synthèse de réponse."""
from __future__ import annotations

import numpy as np
from google import genai
from google.genai import types

from .config import Settings
from .index_store import PageEntry

_ANSWER_PROMPT = """Tu réponds en français à une question sur une revue technique \
automobile (Peugeot 106 / Citroën Saxo), à partir UNIQUEMENT des extraits de pages \
fournis ci-dessous. Cite systématiquement le(s) numéro(s) de page que tu utilises \
réellement dans ta réponse (ex : "(page 42)"). Si les extraits ne permettent pas de \
répondre, dis-le clairement plutôt que d'inventer une réponse.

Question : {query}

Extraits disponibles :
{context}
"""


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


def generate_answer(settings: Settings, query: str, pages: list[PageEntry]) -> str:
    client = _client(settings)
    context = "\n\n".join(f"--- Page {p.page_num} ---\n{p.text}" for p in pages)
    prompt = _ANSWER_PROMPT.format(query=query, context=context)
    response = client.models.generate_content(model=settings.gemini_model, contents=prompt)
    return response.text or ""
