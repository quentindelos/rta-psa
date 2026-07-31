"""Charge l'index (metadata.jsonl + embeddings.npy + manifest.json) depuis GCS et
sert la recherche par similarité cosinus (produit scalaire sur vecteurs déjà normalisés).

Copie volontairement séparée de `ingestion/index_store.py` — le backend déployé et
le pipeline d'ingestion n'ont pas besoin de partager de dépendances.
"""
from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from google.cloud import storage

from .config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageEntry:
    page_num: int
    text: str
    image_filename: str
    has_schematic: bool
    schematic_image_filename: str | None = None


@dataclass(frozen=True)
class SearchHit:
    page: PageEntry
    score: float


class IndexStore:
    def __init__(self) -> None:
        self._pages: list[PageEntry] = []
        self._embeddings: np.ndarray = np.zeros((0, 0), dtype=np.float32)

    def load(self, settings: Settings) -> None:
        client = storage.Client(project=settings.google_cloud_project)
        bucket = client.bucket(settings.gcs_bucket_index)

        if not bucket.blob("index/manifest.json").exists():
            logger.warning(
                "Aucun index trouvé dans gs://%s/index/ — aucune page ingérée pour "
                "l'instant. L'app démarre avec un index vide.",
                settings.gcs_bucket_index,
            )
            self._pages = []
            self._embeddings = np.zeros((0, 0), dtype=np.float32)
            return

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bucket.blob("index/metadata.jsonl").download_to_filename(tmp_path / "metadata.jsonl")
            bucket.blob("index/embeddings.npy").download_to_filename(tmp_path / "embeddings.npy")
            bucket.blob("index/manifest.json").download_to_filename(tmp_path / "manifest.json")

            pages = []
            with (tmp_path / "metadata.jsonl").open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        pages.append(PageEntry(**json.loads(line)))

            embeddings = np.load(tmp_path / "embeddings.npy")
            manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

        if manifest.get("embedding_model") != settings.embedding_model:
            logger.warning(
                "Le modèle d'embedding de l'index (%s) ne correspond pas à la config "
                "du backend (%s) — les scores de similarité seront incohérents.",
                manifest.get("embedding_model"),
                settings.embedding_model,
            )

        self._pages = pages
        self._embeddings = embeddings
        logger.info("Index chargé : %d page(s).", len(pages))

    def search(self, query_vector: np.ndarray, k: int) -> list[SearchHit]:
        if not self._pages:
            return []
        scores = self._embeddings @ query_vector
        top_indices = np.argsort(-scores)[:k]
        return [SearchHit(page=self._pages[i], score=float(scores[i])) for i in top_indices]


index_store = IndexStore()
