from __future__ import annotations

import chromadb
import pytest

from felix.vectorstore.seed import seed_scenes
from felix.vectorstore.store import search_scenes_in_chroma


@pytest.fixture
def collection() -> chromadb.Collection:
    client = chromadb.EphemeralClient()
    col = client.get_or_create_collection(name="scenes_test")
    seed_scenes(col)
    return col


def test_collection_has_all_scenes(collection: chromadb.Collection) -> None:
    assert collection.count() == 5


def test_search_identity_discovery(collection: chromadb.Collection) -> None:
    result = search_scenes_in_chroma(
        collection, query="decouverte identite secrete agent double"
    )
    assert "042" in result or "088" in result


def test_search_with_era_filter(collection: chromadb.Collection) -> None:
    result = search_scenes_in_chroma(
        collection, query="documents archives", era="1970s"
    )
    assert "088" in result
    assert "012" not in result


def test_search_with_character_filter(collection: chromadb.Collection) -> None:
    result = search_scenes_in_chroma(
        collection,
        query="planque",
        characters=["marie_dupont"],
    )
    # Should find scenes where Marie is present
    assert "012" in result or "025" in result or "042" in result


def test_search_no_results(collection: chromadb.Collection) -> None:
    result = search_scenes_in_chroma(
        collection,
        query="dinosaures dans l'espace",
        era="2050s",
    )
    assert "No matching scenes" in result
