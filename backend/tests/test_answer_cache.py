"""Tests unitaires du cache réponses de /api/ask, sans appel GCP réel."""
import time

from app.answer_cache import AnswerCache
from app.models import AskResponse


def _response(text: str = "réponse") -> AskResponse:
    return AskResponse(query="q", answer=text, answer_origin="rta_and_web")


def test_cache_hit_ignores_case_and_whitespace() -> None:
    cache = AnswerCache()
    response = _response()
    cache.set("Quel est le  couple  max ?", "Saxo 1.6i", "essence", response)

    assert cache.get("quel est le couple max ?", "saxo 1.6i", "essence") is response


def test_cache_miss_for_unknown_query() -> None:
    cache = AnswerCache()

    assert cache.get("jamais posée", None, None) is None


def test_cache_distinguishes_by_vehicle() -> None:
    cache = AnswerCache()
    cache.set("dimensions", "Saxo 1.0i", "essence", _response("saxo"))

    assert cache.get("dimensions", "Saxo 1.6i", "essence") is None
    assert cache.get("dimensions", None, "essence") is None


def test_cache_distinguishes_by_fuel() -> None:
    cache = AnswerCache()
    cache.set("dimensions", None, "essence", _response("essence"))

    assert cache.get("dimensions", None, "diesel") is None
    assert cache.get("dimensions", None, None) is None
    assert cache.get("dimensions", None, "essence") is not None


def test_cache_entries_expire_after_ttl() -> None:
    cache = AnswerCache(ttl_seconds=0.01)
    cache.set("q", None, None, _response())

    time.sleep(0.02)

    assert cache.get("q", None, None) is None


def test_cache_evicts_least_recently_used_beyond_maxsize() -> None:
    cache = AnswerCache(maxsize=2)
    cache.set("a", None, None, _response("a"))
    cache.set("b", None, None, _response("b"))
    cache.set("c", None, None, _response("c"))

    assert cache.get("a", None, None) is None
    assert cache.get("b", None, None) is not None
    assert cache.get("c", None, None) is not None


def test_clear_removes_all_entries() -> None:
    cache = AnswerCache()
    cache.set("q", None, None, _response())

    cache.clear()

    assert cache.get("q", None, None) is None
