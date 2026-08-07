from __future__ import annotations

import json
from collections.abc import Iterator

import numpy as np
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..answer_cache import answer_cache
from ..config import Settings, get_settings
from ..index_store import PageEntry, index_store
from ..models import AskResponse, Source, WebSource
from ..vertex import RtaAnswer, embed_query, generate_answer, generate_combined_answer

router = APIRouter()

_EMPTY_RTA_RESULT = RtaAnswer(found=False, answer="")


def _sources_from(result: RtaAnswer, pages: list[PageEntry], settings: Settings) -> list[Source]:
    cited = set(result.cited_pages)
    # Ne garde que les pages effectivement citées dans la réponse — sinon on
    # affiche tout le lot de la recherche, y compris des pages non pertinentes.
    cited_pages = [page for page in pages if page.page_label in cited] or pages
    return [
        Source(
            page_num=page.page_label,
            page_image_url=f"https://storage.googleapis.com/{settings.gcs_bucket_pages}/{page.image_filename}",
            schematic_image_urls=[
                f"https://storage.googleapis.com/{settings.gcs_bucket_pages}/{filename}"
                for filename in page.schematic_image_filenames
            ],
        )
        for page in cited_pages
    ]


def _search_rta(
    settings: Settings, q: str, vehicle: str | None, fuel: str | None, query_vector: np.ndarray, k: int
) -> tuple[RtaAnswer, list[PageEntry]]:
    """Cherche les k pages les plus proches (filtrées par carburant si connu) et tente d'y
    répondre. Renvoie un RtaAnswer(found=False) — jamais None — si la recherche ne remonte
    rien ou si Gemini juge que ça ne répond pas vraiment : la RTA est désormais toujours
    couplée à une recherche web, il n'y a plus de "pas de résultat" côté RTA à propager."""
    hits = index_store.search(query_vector, k, variant=fuel)
    if not hits:
        return _EMPTY_RTA_RESULT, []
    pages = [hit.page for hit in hits]
    result = generate_answer(settings, q, pages, vehicle)
    return (result, pages) if result.found else (_EMPTY_RTA_RESULT, pages)


def _answer_from(
    settings: Settings, q: str, vehicle: str | None, rta_result: RtaAnswer, pages: list[PageEntry]
) -> AskResponse:
    combined_answer, web_sources = generate_combined_answer(settings, q, rta_result, pages, vehicle)
    return AskResponse(
        query=q,
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
    settings: Settings = Depends(get_settings),
) -> AskResponse:
    cached = answer_cache.get(q, vehicle, fuel)
    if cached is not None:
        return cached

    query_vector = embed_query(settings, q)
    top_k = k or settings.top_k_default

    # Les top_k pages les plus proches suffisent la plupart du temps ; si Gemini juge
    # que ça ne répond pas à la question, on élargit avant de considérer que la RTA ne
    # couvre pas le sujet — la bonne page est parfois juste hors du top_k initial.
    rta_result, pages = _search_rta(settings, q, vehicle, fuel, query_vector, top_k)
    if not rta_result.found and top_k < settings.top_k_wide:
        rta_result, pages = _search_rta(settings, q, vehicle, fuel, query_vector, settings.top_k_wide)

    response = _answer_from(settings, q, vehicle, rta_result, pages)
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
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Même recherche que /ask, mais publiée en Server-Sent Events : un évènement
    "step" par étape réelle de la recherche (pas de texte inventé), puis un
    évènement "result" avec la réponse finale au même format que /ask."""

    def generate() -> Iterator[str]:
        cached = answer_cache.get(q, vehicle, fuel)
        if cached is not None:
            yield _sse("step", {"message": "Question déjà posée récemment — réponse en cache, pas de nouvelle recherche."})
            yield _sse("result", cached.model_dump())
            return

        yield _sse("step", {"message": "Recherche des pages les plus proches dans la revue technique…"})
        query_vector = embed_query(settings, q)
        top_k = k or settings.top_k_default
        rta_result, pages = _search_rta(settings, q, vehicle, fuel, query_vector, top_k)

        if rta_result.found:
            yield _sse("step", {"message": f"{len(pages)} page(s) pertinente(s) trouvée(s) dans la revue technique."})
        elif top_k < settings.top_k_wide:
            yield _sse(
                "step",
                {"message": "Rien de concluant dans les pages les plus proches — élargissement de la recherche…"},
            )
            rta_result, pages = _search_rta(settings, q, vehicle, fuel, query_vector, settings.top_k_wide)
            if rta_result.found:
                yield _sse("step", {"message": f"{len(pages)} page(s) pertinente(s) après élargissement."})

        if rta_result.found:
            yield _sse("step", {"message": "Recherche complémentaire sur le web et rédaction de la réponse…"})
        else:
            yield _sse(
                "step",
                {"message": "Non trouvé dans la revue technique — recherche sur le web et rédaction de la réponse…"},
            )

        response = _answer_from(settings, q, vehicle, rta_result, pages)
        answer_cache.set(q, vehicle, fuel, response)
        yield _sse("result", response.model_dump())

    return StreamingResponse(generate(), media_type="text/event-stream")
