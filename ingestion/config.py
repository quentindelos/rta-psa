"""Configuration du pipeline d'ingestion, lue depuis les variables d'environnement (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class Config:
    project_id: str
    region: str
    gemini_model: str
    embedding_model: str
    gcs_bucket_pages: str
    gcs_bucket_index: str


def load_config() -> Config:
    return Config(
        project_id=os.environ["GOOGLE_CLOUD_PROJECT"],
        region=os.environ.get("GOOGLE_CLOUD_REGION", "europe-west1"),
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "text-multilingual-embedding-002"),
        gcs_bucket_pages=os.environ.get("GCS_BUCKET_PAGES", "rta-psa-pages"),
        gcs_bucket_index=os.environ.get("GCS_BUCKET_INDEX", "rta-psa-index"),
    )
