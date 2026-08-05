from fastapi import APIRouter, Depends, Header, HTTPException, status

from ..answer_cache import answer_cache
from ..config import Settings, get_settings
from ..index_store import index_store

router = APIRouter()


@router.post("/admin/reload-index", status_code=status.HTTP_204_NO_CONTENT)
def reload_index(
    x_admin_token: str = Header(...),
    settings: Settings = Depends(get_settings),
) -> None:
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Jeton admin invalide")
    index_store.load(settings)
    # De nouvelles pages ingérées rendent les réponses en cache potentiellement
    # obsolètes (une question "pas dans la RTA" pourrait maintenant y être) - on vide
    # le cache plutôt que d'attendre son expiration naturelle.
    answer_cache.clear()
