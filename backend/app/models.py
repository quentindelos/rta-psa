"""Modèles de réponse de l'API."""
from typing import Literal

from pydantic import BaseModel


class Source(BaseModel):
    page_num: int
    page_image_url: str
    schematic_image_url: str | None = None


class WebSource(BaseModel):
    title: str
    url: str


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
    answer_origin: Literal["rta", "web"]
    sources: list[Source] = []
    web_sources: list[WebSource] = []
