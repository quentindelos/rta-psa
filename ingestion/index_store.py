"""Lecture/écriture de l'index local (metadata.jsonl + embeddings.npy + manifest.json).

Copie volontairement séparée de `backend/app/index_store.py` : l'ingestion et le
backend déployé n'ont pas besoin de partager de dépendances.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


@dataclass
class PageEntry:
    page_num: int
    text: str
    image_filename: str
    has_schematic: bool


@dataclass
class Index:
    pages: list[PageEntry] = field(default_factory=list)
    embeddings: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))
    embedding_model: str | None = None
    gemini_model: str | None = None

    def page_nums(self) -> set[int]:
        return {p.page_num for p in self.pages}

    def upsert(self, entry: PageEntry, embedding: np.ndarray) -> None:
        existing_idx = next((i for i, p in enumerate(self.pages) if p.page_num == entry.page_num), None)
        if existing_idx is not None:
            self.pages[existing_idx] = entry
            self.embeddings[existing_idx] = embedding
        else:
            self.pages.append(entry)
            if self.embeddings.size == 0:
                self.embeddings = embedding.reshape(1, -1)
            else:
                self.embeddings = np.vstack([self.embeddings, embedding])
        self._resort()

    def _resort(self) -> None:
        order = sorted(range(len(self.pages)), key=lambda i: self.pages[i].page_num)
        self.pages = [self.pages[i] for i in order]
        if self.embeddings.size > 0:
            self.embeddings = self.embeddings[order]


def load(index_dir: Path) -> Index:
    metadata_path = index_dir / "metadata.jsonl"
    embeddings_path = index_dir / "embeddings.npy"
    manifest_path = index_dir / "manifest.json"

    if not metadata_path.exists():
        return Index()

    pages = []
    with metadata_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pages.append(PageEntry(**json.loads(line)))

    embeddings = np.load(embeddings_path) if embeddings_path.exists() else np.zeros((0, 0), dtype=np.float32)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    index = Index(
        pages=pages,
        embeddings=embeddings,
        embedding_model=manifest.get("embedding_model"),
        gemini_model=manifest.get("gemini_model"),
    )
    index._resort()
    return index


def save(index: Index, index_dir: Path) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = index_dir / "metadata.jsonl"
    embeddings_path = index_dir / "embeddings.npy"
    manifest_path = index_dir / "manifest.json"

    with metadata_path.open("w", encoding="utf-8") as f:
        for page in index.pages:
            f.write(json.dumps(page.__dict__, ensure_ascii=False) + "\n")

    np.save(embeddings_path, index.embeddings.astype(np.float32))

    manifest = {
        "ingested_pages": [p.page_num for p in index.pages],
        "embedding_model": index.embedding_model,
        "gemini_model": index.gemini_model,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
