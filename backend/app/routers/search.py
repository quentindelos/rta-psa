from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..index_store import index_store
from ..models import SearchResponse, SearchResult
from ..vertex import embed_query

router = APIRouter()

_EXCERPT_LENGTH = 400


def _excerpt(text: str) -> str:
    text = text.strip()
    if len(text) <= _EXCERPT_LENGTH:
        return text
    return text[:_EXCERPT_LENGTH].rsplit(" ", 1)[0] + "…"


@router.get("/search", response_model=SearchResponse)
def search(
    q: str, fuel: str | None = None, k: int | None = None, settings: Settings = Depends(get_settings)
) -> SearchResponse:
    top_k = k or settings.top_k_default
    query_vector = embed_query(settings, q)
    hits = index_store.search(query_vector, top_k, variant=fuel)
    results = [
        SearchResult(
            page_num=hit.page.page_label,
            excerpt=_excerpt(hit.page.text),
            image_url=f"https://storage.googleapis.com/{settings.gcs_bucket_pages}/{hit.page.image_filename}",
            score=hit.score,
        )
        for hit in hits
    ]
    return SearchResponse(query=q, results=results)
