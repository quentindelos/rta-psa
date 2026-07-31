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
    top_k_default: int = 8
    # Utilisé en repli quand les `top_k_default` pages les plus proches ne suffisent
    # pas à répondre — élargit la recherche avant de basculer sur le web.
    top_k_wide: int = 20
    admin_token: str = "change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
