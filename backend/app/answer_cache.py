"""Cache mémoire (par instance Cloud Run, perdu au redémarrage — ça suffit ici, pas
besoin d'un cache partagé pour ce volume de trafic) des réponses de /api/ask.

Politique d'expiration : TTL de 6h (assez long pour absorber les questions répétées
d'une même journée/session sans figer une réponse pour toujours) + éviction LRU au-delà
de _MAX_ENTRIES (borne la mémoire même si beaucoup de questions différentes arrivent).
En plus de ça, clear() est appelé explicitement par /api/admin/reload-index : c'est le
vrai évènement qui rend le cache obsolète (nouvelles pages ingérées), pas juste le temps
qui passe.
"""
from __future__ import annotations

import time
from collections import OrderedDict

from .models import AskResponse

_TTL_SECONDS = 6 * 60 * 60
_MAX_ENTRIES = 500

CacheKey = tuple[str, str, str]


def _normalize(text: str) -> str:
    return " ".join(text.split()).strip().lower()


class AnswerCache:
    def __init__(self, maxsize: int = _MAX_ENTRIES, ttl_seconds: float = _TTL_SECONDS) -> None:
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._data: OrderedDict[CacheKey, tuple[float, AskResponse]] = OrderedDict()

    def _key(self, query: str, vehicle: str | None, fuel: str | None) -> CacheKey:
        # Le carburant fait partie de la clé : il change la moitié de la RTA consultée,
        # deux réponses pour la même question mais un carburant différent ne doivent
        # jamais partager une entrée de cache.
        return (_normalize(query), _normalize(vehicle or ""), _normalize(fuel or ""))

    def get(self, query: str, vehicle: str | None, fuel: str | None = None) -> AskResponse | None:
        key = self._key(query, vehicle, fuel)
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, response = entry
        if time.monotonic() >= expires_at:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return response

    def set(self, query: str, vehicle: str | None, fuel: str | None, response: AskResponse) -> None:
        key = self._key(query, vehicle, fuel)
        self._data[key] = (time.monotonic() + self._ttl, response)
        self._data.move_to_end(key)
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()


answer_cache = AnswerCache()
