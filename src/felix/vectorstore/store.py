from __future__ import annotations

from typing import Any

import chromadb

from felix.config import settings


def get_chroma_client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=settings.chroma_path)


def get_collection(
    client: chromadb.ClientAPI | None = None,
) -> chromadb.Collection:
    if client is None:
        client = get_chroma_client()
    return client.get_or_create_collection(name="scenes")


def search_scenes_in_chroma(
    collection: chromadb.Collection,
    query: str,
    n_results: int = 5,
    era: str | None = None,
    characters: list[str] | None = None,
) -> str:
    where_clauses: list[dict[str, Any]] = []

    if era:
        where_clauses.append({"era": era})
    if characters:
        for char_slug in characters:
            where_clauses.append({f"char_{char_slug}": True})

    where: dict[str, Any] | None = None
    if len(where_clauses) > 1:
        where = {"$and": where_clauses}
    elif len(where_clauses) == 1:
        where = where_clauses[0]

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    documents = results.get("documents") or [[]]
    metadatas = results.get("metadatas") or [[]]
    distances = results.get("distances") or [[]]

    if not documents[0]:
        return "No matching scenes found."

    lines = [f"Found {len(documents[0])} relevant scene(s):"]
    for doc, raw_meta, dist in zip(
        documents[0], metadatas[0], distances[0], strict=True
    ):
        meta = raw_meta or {}
        scene_id = meta.get("scene_id", "?")
        scene_era = meta.get("era", "?")
        location = meta.get("location_id", "?")

        present_chars = [
            key.removeprefix("char_")
            for key, val in meta.items()
            if key.startswith("char_") and val is True
        ]

        lines.append(
            f"\n--- Scene {scene_id} (era: {scene_era}, location: {location}, distance: {dist:.3f}) ---"
        )
        if present_chars:
            lines.append(f"Characters present: {', '.join(present_chars)}")
        lines.append(str(doc))

    return "\n".join(lines)
