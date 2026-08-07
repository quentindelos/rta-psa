"""Tests unitaires du classement de recherche, sans appel GCP réel."""
import numpy as np

from app.index_store import IndexStore, PageEntry


def _make_store() -> IndexStore:
    store = IndexStore()
    store._pages = [
        PageEntry(page_num=1, text="démarreur", image_filename="page_001.jpg", has_schematic=False),
        PageEntry(page_num=2, text="alternateur", image_filename="page_002.jpg", has_schematic=True),
    ]
    store._embeddings = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    return store


def _make_variant_store() -> IndexStore:
    store = IndexStore()
    store._pages = [
        PageEntry(page_num=1, text="essence", image_filename="essence/page_I.jpg", has_schematic=False, variant="essence"),
        PageEntry(page_num=2, text="diesel", image_filename="diesel/page_I.jpg", has_schematic=False, variant="diesel"),
        PageEntry(page_num=3, text="commun", image_filename="commun/page_001.jpg", has_schematic=False, variant="commun"),
    ]
    store._embeddings = np.array([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    return store


def test_search_returns_best_match_first() -> None:
    store = _make_store()
    query_vector = np.array([0.9, 0.1], dtype=np.float32)

    hits = store.search(query_vector, k=2)

    assert [hit.page.page_num for hit in hits] == [1, 2]


def test_search_respects_k() -> None:
    store = _make_store()
    query_vector = np.array([0.0, 1.0], dtype=np.float32)

    hits = store.search(query_vector, k=1)

    assert len(hits) == 1
    assert hits[0].page.page_num == 2


def test_search_on_empty_store_returns_no_hits() -> None:
    store = IndexStore()

    hits = store.search(np.array([1.0, 0.0], dtype=np.float32), k=5)

    assert hits == []


def test_search_without_variant_returns_all_pages() -> None:
    store = _make_variant_store()

    hits = store.search(np.array([1.0, 0.0], dtype=np.float32), k=3)

    assert {hit.page.variant for hit in hits} == {"essence", "diesel", "commun"}


def test_search_with_variant_excludes_other_fuel_but_keeps_commun() -> None:
    store = _make_variant_store()

    hits = store.search(np.array([1.0, 0.0], dtype=np.float32), k=3, variant="diesel")

    assert {hit.page.variant for hit in hits} == {"diesel", "commun"}
