"""Point d'entrée FastAPI : API de recherche/question + fichiers statiques du frontend."""
import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from .config import get_settings
from .index_store import index_store
from .routers import admin, ask, search

logging.basicConfig(level=logging.INFO)


class NoCacheStaticFiles(StaticFiles):
    """Force la revalidation (ETag) à chaque requête au lieu de laisser le
    navigateur mettre en cache une version périmée de style.css/app.js après
    un déploiement — sans Cache-Control, le cache heuristique du navigateur
    peut servir une ancienne version pendant un moment."""

    def file_response(self, full_path: os.PathLike, *args, **kwargs) -> Response:
        response = super().file_response(full_path, *args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response

app = FastAPI(title="RTA 106/Saxo — recherche")

app.include_router(search.router, prefix="/api")
app.include_router(ask.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.on_event("startup")
def load_index() -> None:
    index_store.load(get_settings())


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# En image Docker, le frontend est copié dans app/static au build. En local (sans
# build Docker), on retombe sur le dossier frontend/ du monorepo pour pouvoir
# tester avec `uvicorn app.main:app --reload` directement.
_static_dir = Path(__file__).resolve().parent / "static"
if not _static_dir.exists():
    _static_dir = Path(__file__).resolve().parent.parent.parent / "frontend"

app.mount("/", NoCacheStaticFiles(directory=str(_static_dir), html=True), name="static")
