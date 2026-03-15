from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiosqlite
    import chromadb

    from felix.ingest.resolver import ResolvedEntity

from felix.db.repository import (
    upsert_character_event,
    upsert_character_fragment,
    upsert_character_minimal,
    upsert_location_minimal,
    upsert_scene,
    upsert_timeline_event,
)


async def load_scene(  # noqa: PLR0913
    db: aiosqlite.Connection,
    collection: chromadb.Collection,
    scene_id: str,
    filename: str,
    scene_text: str,
    analysis: Any,
    resolved_chars: list[tuple[ResolvedEntity, str, str | None]],
    resolved_location: ResolvedEntity,
) -> None:
    # 1. Upsert scene
    await upsert_scene(db, {
        "id": scene_id,
        "filename": filename,
        "title": analysis.title,
        "summary": analysis.summary,
        "era": analysis.era,
        "date": analysis.approximate_date,
        "location_id": resolved_location.id,
        "raw_text": scene_text,
    })

    # 2. Upsert location (INSERT OR IGNORE)
    await upsert_location_minimal(db, {
        "id": resolved_location.id,
        "name": resolved_location.name,
        "description": analysis.location.description,
    })

    # 3. Upsert characters (INSERT OR IGNORE) + fragments
    for resolved_char, role, description in resolved_chars:
        await upsert_character_minimal(db, {
            "id": resolved_char.id,
            "name": resolved_char.name,
            "era": analysis.era,
        })
        await upsert_character_fragment(
            db, resolved_char.id, scene_id, role, description
        )

    # 4. Upsert timeline event
    date = analysis.approximate_date
    if not date and analysis.era:
        # Fallback: extract year from era like "1940s" → "1940-01-01"
        era_digits = "".join(c for c in analysis.era if c.isdigit())
        if era_digits:
            date = f"{era_digits[:4]}-01-01"
    await upsert_timeline_event(db, {
        "id": f"evt-{scene_id}",
        "date": date or "unknown",
        "era": analysis.era,
        "title": analysis.title,
        "description": analysis.summary,
        "location_id": resolved_location.id,
        "scene_id": scene_id,
    })

    # 5. Upsert character events
    for resolved_char, role, _desc in resolved_chars:
        await upsert_character_event(
            db, resolved_char.id, f"evt-{scene_id}", role
        )

    # 6. ChromaDB upsert
    metadata: dict[str, str | bool] = {
        "scene_id": scene_id,
        "era": analysis.era,
        "location_id": resolved_location.id,
    }
    for resolved_char, _role, _desc in resolved_chars:
        metadata[f"char_{resolved_char.id}"] = True

    collection.upsert(
        ids=[scene_id],
        documents=[scene_text],
        metadatas=[metadata],
    )
