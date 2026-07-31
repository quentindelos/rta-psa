"""Configuration du backend (variables d'environnement / .env local)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_cloud_project: str
    google_cloud_region: str = "europe-west1"
    gcs_bucket_index: str = "rta-psa-index"
    gcs_bucket_pages: str = "rta-psa-pages"
    gemini_model: str = "gemini-2.5-flash"
    embedding_model: str = "text-multilingual-embedding-002"
    top_k_default: int = 5
    admin_token: str = "change-me"
    rta_confidence_threshold: float = 0.45


@lru_cache
def get_settings() -> Settings:
    return Settings()
