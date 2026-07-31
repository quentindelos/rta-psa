"""Modèles de réponse de l'API."""
from pydantic import BaseModel


class Source(BaseModel):
    page_num: int
    page_image_url: str
    schematic_image_url: str | None = None


class SearchResult(BaseModel):
    page_num: int
    excerpt: str
    image_url: str
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


class AskResponse(BaseModel):
    query: str
    answer: str
    sources: list[Source]
