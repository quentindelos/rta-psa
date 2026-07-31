"""Tests unitaires du cache réponses de /api/ask, sans appel GCP réel."""
import time

from app.answer_cache import AnswerCache
from app.models import AskResponse


def _response(text: str = "réponse") -> AskResponse:
    return AskResponse(query="q", answer=text, answer_origin="rta")


def test_cache_hit_ignores_case_and_whitespace() -> None:
    cache = AnswerCache()
    response = _response()
    cache.set("Quel est le  couple  max ?", "Saxo 1.6i", response)

    assert cache.get("quel est le couple max ?", "saxo 1.6i") is response


def test_cache_miss_for_unknown_query() -> None:
    cache = AnswerCache()

    assert cache.get("jamais posée", None) is None


def test_cache_distinguishes_by_vehicle() -> None:
    cache = AnswerCache()
    cache.set("dimensions", "Saxo 1.0i", _response("saxo"))

    assert cache.get("dimensions", "Saxo 1.6i") is None
    assert cache.get("dimensions", None) is None


def test_cache_entries_expire_after_ttl() -> None:
    cache = AnswerCache(ttl_seconds=0.01)
    cache.set("q", None, _response())

    time.sleep(0.02)

    assert cache.get("q", None) is None


def test_cache_evicts_least_recently_used_beyond_maxsize() -> None:
    cache = AnswerCache(maxsize=2)
    cache.set("a", None, _response("a"))
    cache.set("b", None, _response("b"))
    cache.set("c", None, _response("c"))

    assert cache.get("a", None) is None
    assert cache.get("b", None) is not None
    assert cache.get("c", None) is not None


def test_clear_removes_all_entries() -> None:
    cache = AnswerCache()
    cache.set("q", None, _response())

    cache.clear()

    assert cache.get("q", None) is None
