from __future__ import annotations

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..answer_cache import answer_cache
from ..config import Settings, get_settings
from ..index_store import PageEntry, index_store
from ..models import AskResponse, Highlight, HistoryTurn, Source, WebSource
from ..vertex import (
    RtaAnswer,
    contextualize_query,
    embed_query,
    generate_answer,
    generate_combined_answer,
    generate_title,
    locate_highlight,
)

router = APIRouter()

_EMPTY_RTA_RESULT = RtaAnswer(found=False, answer="")
# Nombre de tours précédents effectivement transmis aux prompts - suffisant pour garder
# le fil d'une conversation de suivi sans faire grossir indéfiniment le contexte envoyé
# à Gemini (et la query string du client, l'historique voyageant en paramètre GET).
_MAX_HISTORY_TURNS = 4


def _parse_history(raw: str | None) -> list[HistoryTurn]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    turns: list[HistoryTurn] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        query = str(item.get("q") or "").strip()
        answer = str(item.get("a") or "").strip()
        if query and answer:
            turns.append(HistoryTurn(query=query, answer=answer))
    return turns[-_MAX_HISTORY_TURNS:]


def _sources_from(result: RtaAnswer, pages: list[PageEntry], settings: Settings) -> list[Source]:
    cited = set(result.cited_pages)
    # Ne garde que les pages effectivement citées dans la réponse - sinon on
    # affiche tout le lot de la recherche, y compris des pages non pertinentes.
    cited_pages = [page for page in pages if page.page_label in cited] or pages

    # Un appel Gemini (vision) par schéma pour repérer la zone à mettre en évidence -
    # en parallèle, sinon une réponse citant plusieurs schémas deviendrait lente (chaque
    # appel prend une seconde ou deux). Best-effort : voir locate_highlight, jamais
    # bloquant pour l'affichage des sources elles-mêmes.
    jobs = [
        (page_idx, schematic_idx, f"gs://{settings.gcs_bucket_pages}/{filename}")
        for page_idx, page in enumerate(cited_pages)
        for schematic_idx, filename in enumerate(page.schematic_image_filenames)
    ]
    highlights: dict[tuple[int, int], Highlight | None] = {}
    if jobs:
        with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as executor:
            futures = {
                executor.submit(locate_highlight, settings, gcs_uri, result.answer): (page_idx, schematic_idx)
                for page_idx, schematic_idx, gcs_uri in jobs
            }
            for future, key in futures.items():
                highlights[key] = future.result()

    return [
        Source(
            page_num=page.page_label,
            page_image_url=f"https://storage.googleapis.com/{settings.gcs_bucket_pages}/{page.image_filename}",
            schematic_image_urls=[
                f"https://storage.googleapis.com/{settings.gcs_bucket_pages}/{filename}"
                for filename in page.schematic_image_filenames
            ],
            schematic_highlights=[
                highlights.get((page_idx, schematic_idx))
                for schematic_idx in range(len(page.schematic_image_filenames))
            ],
        )
        for page_idx, page in enumerate(cited_pages)
    ]


def _search_rta(
    settings: Settings,
    q: str,
    vehicle: str | None,
    fuel: str | None,
    query_vector: np.ndarray,
    k: int,
    history: list[HistoryTurn],
) -> tuple[RtaAnswer, list[PageEntry]]:
    """Cherche les k pages les plus proches (filtrées par carburant si connu) et tente d'y
    répondre. Renvoie un RtaAnswer(found=False) - jamais None - si la recherche ne remonte
    rien ou si Gemini juge que ça ne répond pas vraiment : la RTA est désormais toujours
    couplée à une recherche web, il n'y a plus de "pas de résultat" côté RTA à propager."""
    hits = index_store.search(query_vector, k, variant=fuel)
    if not hits:
        return _EMPTY_RTA_RESULT, []
    pages = [hit.page for hit in hits]
    result = generate_answer(settings, q, pages, vehicle, history)
    return (result, pages) if result.found else (_EMPTY_RTA_RESULT, pages)


def _answer_from(
    settings: Settings,
    q: str,
    title: str,
    vehicle: str | None,
    fuel: str | None,
    rta_result: RtaAnswer,
    pages: list[PageEntry],
    history: list[HistoryTurn],
) -> AskResponse:
    combined_answer, web_sources = generate_combined_answer(settings, q, rta_result, pages, vehicle, fuel, history)
    return AskResponse(
        query=q,
        title=title,
        answer=combined_answer,
        answer_origin="rta_and_web" if rta_result.found else "web_only",
        sources=_sources_from(rta_result, pages, settings) if rta_result.found else [],
        web_sources=[WebSource(title=s.title, url=s.url) for s in web_sources],
    )


@router.get("/ask", response_model=AskResponse)
def ask(
    q: str,
    vehicle: str | None = None,
    fuel: str | None = None,
    k: int | None = None,
    history: str | None = None,
    settings: Settings = Depends(get_settings),
) -> AskResponse:
    turns = _parse_history(history)
    # Une conversation de suivi dépend de son historique : la même question littérale peut
    # appeler une réponse différente selon ce qui précède, donc pas de cache dans ce cas
    # (voir answer_cache.py, la clé n'intègre pas l'historique).
    if not turns:
        cached = answer_cache.get(q, vehicle, fuel)
        if cached is not None:
            return cached

    search_query = contextualize_query(settings, q, turns)
    query_vector = embed_query(settings, search_query)
    top_k = k or settings.top_k_default
    title = generate_title(settings, q, vehicle)

    # Les top_k pages les plus proches suffisent la plupart du temps ; si Gemini juge
    # que ça ne répond pas à la question, on élargit avant de considérer que la RTA ne
    # couvre pas le sujet - la bonne page est parfois juste hors du top_k initial.
    rta_result, pages = _search_rta(settings, q, vehicle, fuel, query_vector, top_k, turns)
    if not rta_result.found and top_k < settings.top_k_wide:
        rta_result, pages = _search_rta(settings, q, vehicle, fuel, query_vector, settings.top_k_wide, turns)
    if not rta_result.found and fuel:
        # Rien de spécifique côté {fuel} : beaucoup de chapitres (freins, carrosserie,
        # direction...) sont identiques entre essence et diesel - on retente sans filtre
        # carburant avant d'abandonner la RTA (voir _rta_context pour l'avertissement
        # ajouté au prompt dans ce cas).
        rta_result, pages = _search_rta(settings, q, vehicle, None, query_vector, settings.top_k_wide, turns)

    response = _answer_from(settings, q, title, vehicle, fuel, rta_result, pages, turns)
    if not turns:
        answer_cache.set(q, vehicle, fuel, response)
    return response


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/ask/stream")
def ask_stream(
    q: str,
    vehicle: str | None = None,
    fuel: str | None = None,
    k: int | None = None,
    history: str | None = None,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Même recherche que /ask, mais publiée en Server-Sent Events : un évènement
    "step" par étape réelle de la recherche (pas de texte inventé), puis un
    évènement "result" avec la réponse finale au même format que /ask."""

    def generate() -> Iterator[str]:
        turns = _parse_history(history)

        if not turns:
            cached = answer_cache.get(q, vehicle, fuel)
            if cached is not None:
                yield _sse("step", {"message": "Question déjà posée récemment - réponse en cache, pas de nouvelle recherche."})
                yield _sse("result", cached.model_dump())
                return

        yield _sse("step", {"message": "Recherche des pages les plus proches dans la revue technique…"})
        search_query = contextualize_query(settings, q, turns)
        query_vector = embed_query(settings, search_query)
        top_k = k or settings.top_k_default
        title = generate_title(settings, q, vehicle)
        rta_result, pages = _search_rta(settings, q, vehicle, fuel, query_vector, top_k, turns)

        if rta_result.found:
            yield _sse("step", {"message": f"{len(pages)} page(s) pertinente(s) trouvée(s) dans la revue technique."})
        elif top_k < settings.top_k_wide:
            yield _sse(
                "step",
                {"message": "Rien de concluant dans les pages les plus proches - élargissement de la recherche…"},
            )
            rta_result, pages = _search_rta(settings, q, vehicle, fuel, query_vector, settings.top_k_wide, turns)
            if rta_result.found:
                yield _sse("step", {"message": f"{len(pages)} page(s) pertinente(s) après élargissement."})

        if not rta_result.found and fuel:
            yield _sse(
                "step",
                {"message": "Rien de spécifique côté carburant précisé - recherche dans l'autre motorisation…"},
            )
            rta_result, pages = _search_rta(settings, q, vehicle, None, query_vector, settings.top_k_wide, turns)
            if rta_result.found:
                yield _sse("step", {"message": f"{len(pages)} page(s) pertinente(s) trouvée(s) (autre motorisation)."})

        if rta_result.found:
            yield _sse("step", {"message": "Recherche complémentaire sur le web et rédaction de la réponse…"})
        else:
            yield _sse(
                "step",
                {"message": "Non trouvé dans la revue technique - recherche sur le web et rédaction de la réponse…"},
            )

        response = _answer_from(settings, q, title, vehicle, fuel, rta_result, pages, turns)
        if not turns:
            answer_cache.set(q, vehicle, fuel, response)
        yield _sse("result", response.model_dump())

    return StreamingResponse(generate(), media_type="text/event-stream")
