"""Point d'entrée FastAPI : API de recherche/question + fichiers statiques du frontend."""
import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from .config import get_settings
from .index_store import index_store
from .routers import admin, ask, search

logging.basicConfig(level=logging.INFO)


class NoCacheStaticFiles(StaticFiles):
    """Force la revalidation (ETag) à chaque requête au lieu de laisser le
    navigateur mettre en cache une version périmée de style.css/app.js après
    un déploiement - sans Cache-Control, le cache heuristique du navigateur
    peut servir une ancienne version pendant un moment.

    Sert aussi les pages .html sans l'extension dans l'URL (/fonctionnement plutôt
    que /fonctionnement.html) : si le chemin demandé n'a pas d'extension et ne
    correspond à aucun fichier, on retente avec ".html" avant d'abandonner en 404."""

    def file_response(self, full_path: os.PathLike, *args, **kwargs) -> Response:
        response = super().file_response(full_path, *args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            last_segment = path.rsplit("/", 1)[-1]
            if exc.status_code == 404 and path and "." not in last_segment:
                return await super().get_response(f"{path}.html", scope)
            raise

app = FastAPI(title="RTA 106/Saxo - recherche")

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
