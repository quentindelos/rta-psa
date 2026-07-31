from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..index_store import index_store
from ..models import AskResponse, Source, WebSource
from ..vertex import embed_query, generate_answer, generate_web_answer

router = APIRouter()


@router.get("/ask", response_model=AskResponse)
def ask(q: str, k: int | None = None, settings: Settings = Depends(get_settings)) -> AskResponse:
    top_k = k or settings.top_k_default
    query_vector = embed_query(settings, q)
    hits = index_store.search(query_vector, top_k)

    best_score = hits[0].score if hits else -1.0
    if hits and best_score >= settings.rta_confidence_threshold:
        pages = [hit.page for hit in hits]
        answer = generate_answer(settings, q, pages)
        sources = [
            Source(
                page_num=page.page_num,
                page_image_url=f"https://storage.googleapis.com/{settings.gcs_bucket_pages}/{page.image_filename}",
                schematic_image_url=(
                    f"https://storage.googleapis.com/{settings.gcs_bucket_pages}/{page.schematic_image_filename}"
                    if page.schematic_image_filename
                    else None
                ),
            )
            for page in pages
        ]
        return AskResponse(query=q, answer=answer, answer_origin="rta", sources=sources)

    answer, web_sources = generate_web_answer(settings, q)
    return AskResponse(
        query=q,
        answer=answer,
        answer_origin="web",
        web_sources=[WebSource(title=s.title, url=s.url) for s in web_sources],
    )
