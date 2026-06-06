from __future__ import annotations

from typing import Annotated

import chromadb
from protest import ProTestSuite, Use, fixture

from felix.vectorstore.seed import seed_scenes
from felix.vectorstore.store import search_scenes_in_chroma

vectorstore_suite = ProTestSuite("Vectorstore")


@fixture(max_concurrency=1, tags=["chromadb"])
def chroma_collection() -> chromadb.Collection:
    client = chromadb.EphemeralClient()
    col = client.get_or_create_collection(name="scenes_test")
    seed_scenes(col)
    return col


@vectorstore_suite.test()
def test_collection_has_all_scenes(
    collection: Annotated[chromadb.Collection, Use(chroma_collection)],
) -> None:
    assert collection.count() == 5


@vectorstore_suite.test()
def test_search_identity_discovery(
    collection: Annotated[chromadb.Collection, Use(chroma_collection)],
) -> None:
    result = search_scenes_in_chroma(
        collection, query="discovery secret identity double agent"
    )
    assert "042" in result or "088" in result


@vectorstore_suite.test()
def test_search_with_era_filter(
    collection: Annotated[chromadb.Collection, Use(chroma_collection)],
) -> None:
    result = search_scenes_in_chroma(
        collection, query="documents archives", era="1970s"
    )
    assert "088" in result
    assert "012" not in result


@vectorstore_suite.test()
def test_search_with_character_filter(
    collection: Annotated[chromadb.Collection, Use(chroma_collection)],
) -> None:
    result = search_scenes_in_chroma(
        collection,
        query="planque",
        characters=["marie_dupont"],
    )
    # Should find scenes where Marie is present
    assert "012" in result or "025" in result or "042" in result


@vectorstore_suite.test()
def test_search_no_results(
    collection: Annotated[chromadb.Collection, Use(chroma_collection)],
) -> None:
    result = search_scenes_in_chroma(
        collection,
        query="dinosaures dans l'espace",
        era="2050s",
    )
    assert "No matching scenes" in result
