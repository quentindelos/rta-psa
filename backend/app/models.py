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
    title: str = ""
    answer: str
    # "rta_and_web" : la RTA couvrait le sujet, la réponse combine RTA + web.
    # "web_only" : la RTA ne couvre pas le sujet, réponse basée sur le web uniquement.
    answer_origin: Literal["rta_and_web", "web_only"]
    sources: list[Source] = []
    web_sources: list[WebSource] = []
