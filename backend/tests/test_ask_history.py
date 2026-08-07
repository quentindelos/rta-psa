"""Tests unitaires du parsing de l'historique de conversation reçu par /api/ask(/stream)."""
import json

from app.routers.ask import _MAX_HISTORY_TURNS, _parse_history


def test_parse_history_none_returns_empty() -> None:
    assert _parse_history(None) == []


def test_parse_history_invalid_json_returns_empty() -> None:
    assert _parse_history("not json") == []


def test_parse_history_ignores_entries_missing_query_or_answer() -> None:
    raw = json.dumps([{"q": "couple max"}, {"a": "180 Nm"}, {"q": "ok", "a": "oui"}])

    turns = _parse_history(raw)

    assert len(turns) == 1
    assert turns[0].query == "ok"
    assert turns[0].answer == "oui"


def test_parse_history_keeps_only_last_turns() -> None:
    raw = json.dumps([{"q": f"q{i}", "a": f"a{i}"} for i in range(10)])

    turns = _parse_history(raw)

    assert len(turns) == _MAX_HISTORY_TURNS
    assert [t.query for t in turns] == [f"q{i}" for i in range(10 - _MAX_HISTORY_TURNS, 10)]
