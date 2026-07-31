"""Modèles de réponse de l'API."""
from typing import Literal

from pydantic import BaseModel


class Source(BaseModel):
    page_num: str
    page_image_url: str
    schematic_image_urls: list[str] = []


class WebSource(BaseModel):
    title: str
    url: str


class SearchResult(BaseModel):
    page_num: str
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
