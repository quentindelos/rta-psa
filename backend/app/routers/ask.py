from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..index_store import index_store
from ..models import AskResponse
from ..vertex import embed_query, generate_answer

router = APIRouter()


@router.get("/ask", response_model=AskResponse)
def ask(q: str, k: int | None = None, settings: Settings = Depends(get_settings)) -> AskResponse:
    top_k = k or settings.top_k_default
    query_vector = embed_query(settings, q)
    hits = index_store.search(query_vector, top_k)
    pages = [hit.page for hit in hits]
    answer = generate_answer(settings, q, pages)
    return AskResponse(query=q, answer=answer, sources=[p.page_num for p in pages])
