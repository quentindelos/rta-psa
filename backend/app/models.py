"""Modèles de réponse de l'API."""
from typing import Literal

from pydantic import BaseModel


class Highlight(BaseModel):
    """Zone d'un schéma à mettre en évidence (coordonnées normalisées 0-1, origine en
    haut à gauche) - repérée par Gemini (vision) comme étant la partie du schéma qui
    illustre concrètement la réponse donnée."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float


class Source(BaseModel):
    page_num: str
    page_image_url: str
    schematic_image_urls: list[str] = []
    # Même longueur/ordre que schematic_image_urls ; None si aucune zone précise n'a pu
    # être repérée pour ce schéma (le schéma reste affiché normalement dans ce cas).
    schematic_highlights: list[Highlight | None] = []


class WebSource(BaseModel):
    title: str
    url: str


class HistoryTurn(BaseModel):
    """Un tour précédent de la conversation, envoyé par le client pour qu'une question
    de suivi ("et pour le diesel ?") puisse être comprise sans tout reformuler."""

    query: str
    answer: str


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
