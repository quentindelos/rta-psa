"""Point d'entrée FastAPI : API de recherche/question + fichiers statiques du frontend."""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .index_store import index_store
from .routers import admin, ask, search

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="RTA 106/Saxo — recherche")

app.include_router(search.router, prefix="/api")
app.include_router(ask.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.on_event("startup")
def load_index() -> None:
    index_store.load(get_settings())


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# En image Docker, le frontend est copié dans app/static au build. En local (sans
# build Docker), on retombe sur le dossier frontend/ du monorepo pour pouvoir
# tester avec `uvicorn app.main:app --reload` directement.
_static_dir = Path(__file__).resolve().parent / "static"
if not _static_dir.exists():
    _static_dir = Path(__file__).resolve().parent.parent.parent / "frontend"

app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
