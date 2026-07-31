from __future__ import annotations

import json
from collections.abc import Iterator

import numpy as np
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..config import Settings, get_settings
from ..index_store import PageEntry, index_store
from ..models import AskResponse, Source, WebSource
from ..vertex import RtaAnswer, embed_query, generate_answer, generate_web_answer

router = APIRouter()


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


def _try_rta(
    settings: Settings, q: str, vehicle: str | None, query_vector: np.ndarray, k: int
) -> tuple[RtaAnswer, list[PageEntry]] | None:
    """Cherche les k pages les plus proches et tente d'y répondre. Renvoie None si
    la recherche ne remonte rien ou si Gemini juge que ça ne répond pas vraiment."""
    hits = index_store.search(query_vector, k)
    if not hits:
        return None
    pages = [hit.page for hit in hits]
    result = generate_answer(settings, q, pages, vehicle)
    return (result, pages) if result.found else None


@router.get("/ask", response_model=AskResponse)
def ask(
    q: str, vehicle: str | None = None, k: int | None = None, settings: Settings = Depends(get_settings)
) -> AskResponse:
    query_vector = embed_query(settings, q)
    top_k = k or settings.top_k_default

    # Les top_k pages les plus proches suffisent la plupart du temps ; si Gemini juge
    # que ça ne répond pas à la question, on élargit avant d'abandonner la RTA — la
    # bonne page est parfois juste hors du top_k initial.
    found = _try_rta(settings, q, vehicle, query_vector, top_k)
    if found is None and top_k < settings.top_k_wide:
        found = _try_rta(settings, q, vehicle, query_vector, settings.top_k_wide)

    if found is not None:
        result, pages = found
        return AskResponse(
            query=q, answer=result.answer, answer_origin="rta", sources=_sources_from(result, pages, settings)
        )

    answer, web_sources = generate_web_answer(settings, q, vehicle)
    return AskResponse(
        query=q,
        answer=answer,
        answer_origin="web",
        web_sources=[WebSource(title=s.title, url=s.url) for s in web_sources],
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/ask/stream")
def ask_stream(
    q: str, vehicle: str | None = None, k: int | None = None, settings: Settings = Depends(get_settings)
) -> StreamingResponse:
    """Même recherche que /ask, mais publiée en Server-Sent Events : un évènement
    "step" par étape réelle de la recherche (pas de texte inventé), puis un
    évènement "result" avec la réponse finale au même format que /ask."""

    def generate() -> Iterator[str]:
        yield _sse("step", {"message": "Recherche des pages les plus proches dans la revue technique…"})
        query_vector = embed_query(settings, q)
        top_k = k or settings.top_k_default
        hits = index_store.search(query_vector, top_k)

        result: RtaAnswer | None = None
        pages: list[PageEntry] = []
        if hits:
            pages = [hit.page for hit in hits]
            yield _sse("step", {"message": f"{len(pages)} page(s) trouvée(s) — lecture et rédaction de la réponse…"})
            result = generate_answer(settings, q, pages, vehicle)

        if (result is None or not result.found) and top_k < settings.top_k_wide:
            yield _sse(
                "step",
                {"message": "Rien de concluant dans les pages les plus proches — élargissement de la recherche…"},
            )
            wide_hits = index_store.search(query_vector, settings.top_k_wide)
            if wide_hits:
                pages = [hit.page for hit in wide_hits]
                yield _sse("step", {"message": f"{len(pages)} page(s) après élargissement — nouvelle lecture…"})
                result = generate_answer(settings, q, pages, vehicle)
            else:
                result = None

        if result is not None and result.found:
            yield _sse("step", {"message": "Réponse trouvée dans la revue technique."})
            response = AskResponse(
                query=q, answer=result.answer, answer_origin="rta", sources=_sources_from(result, pages, settings)
            )
            yield _sse("result", response.model_dump())
            return

        yield _sse("step", {"message": "Non trouvé dans la revue technique — recherche sur le web…"})
        answer, web_sources = generate_web_answer(settings, q, vehicle)
        response = AskResponse(
            query=q,
            answer=answer,
            answer_origin="web",
            web_sources=[WebSource(title=s.title, url=s.url) for s in web_sources],
        )
        yield _sse("result", response.model_dump())

    return StreamingResponse(generate(), media_type="text/event-stream")
