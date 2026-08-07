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
    # Volontairement large : la RTA scindée essence/diesel réduit déjà le champ de
    # recherche par deux, et Gemini n'est plus limité dans le nombre de pages qu'il
    # peut citer (voir _ANSWER_PROMPT) - plus de contexte en entrée permet de trouver
    # des réponses à des questions vagues ou dont l'info est éparpillée sur plusieurs
    # pages, sans risque de "diluer" la réponse.
    top_k_default: int = 12
    # Utilisé en repli quand les `top_k_default` pages les plus proches ne suffisent
    # pas à répondre - élargit la recherche avant de basculer sur le web.
    top_k_wide: int = 32
    admin_token: str = "change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
