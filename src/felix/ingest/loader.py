from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import chromadb
    from neo4j import AsyncDriver

    from felix.ingest.resolver import ResolvedEntity

from felix.graph.repositories.characters import (
    upsert_character_fragment,
    upsert_character_minimal,
)
from felix.graph.repositories.groups import upsert_group_in_scene, upsert_group_minimal
from felix.graph.repositories.locations import upsert_location_minimal
from felix.graph.repositories.scenes import upsert_scene
from felix.graph.repositories.timeline import upsert_character_event, upsert_timeline_event


async def load_scene(  # noqa: PLR0913
    driver: AsyncDriver,
    collection: chromadb.Collection,
    scene_id: str,
    filename: str,
    scene_text: str,
    analysis: Any,
    resolved_chars: list[tuple[ResolvedEntity, str, str | None, str | None]],
    resolved_location: ResolvedEntity,
    resolved_groups: list[tuple[ResolvedEntity, str, str | None, str | None]] | None = None,
) -> None:
    # 1. Upsert location (MERGE — must exist before scene AT_LOCATION)
    await upsert_location_minimal(driver, {
        "id": resolved_location.id,
        "name": resolved_location.name,
        "description": analysis.location.description,
    })

    # 2. Upsert scene
    await upsert_scene(driver, {
        "id": scene_id,
        "filename": filename,
        "title": analysis.title,
        "summary": analysis.summary,
        "era": analysis.era,
        "date": analysis.approximate_date,
        "location_id": resolved_location.id,
        "raw_text": scene_text,
    })

    # 3. Upsert characters (MERGE) + fragments (PRESENT_IN)
    for resolved_char, role, description, context in resolved_chars:
        await upsert_character_minimal(driver, {
            "id": resolved_char.id,
            "name": resolved_char.name,
            "era": analysis.era,
        })
        await upsert_character_fragment(
            driver, resolved_char.id, scene_id, role, description, context
        )

    # 3b. Upsert groups (MERGE :Group) + PRESENT_IN
    for resolved_group, role, description, context in (resolved_groups or []):
        await upsert_group_minimal(driver, {
            "id": resolved_group.id,
            "name": resolved_group.name,
            "era": analysis.era,
        })
        await upsert_group_in_scene(driver, resolved_group.id, scene_id, role, description, context)

    # 4. Upsert timeline event
    date = analysis.approximate_date
    if not date and analysis.era:
        era_digits = "".join(c for c in analysis.era if c.isdigit())
        if era_digits:
            date = f"{era_digits[:4]}-01-01"
    await upsert_timeline_event(driver, {
        "id": f"evt-{scene_id}",
        "date": date or "unknown",
        "era": analysis.era,
        "title": analysis.title,
        "description": analysis.summary,
        "location_id": resolved_location.id,
        "scene_id": scene_id,
    })

    # 5. Upsert character events
    for resolved_char, role, _desc, _ctx in resolved_chars:
        await upsert_character_event(
            driver, resolved_char.id, f"evt-{scene_id}", role
        )

    # 6. ChromaDB upsert
    metadata: dict[str, str | bool] = {
        "scene_id": scene_id,
        "era": analysis.era,
        "location_id": resolved_location.id,
    }
    for resolved_char, _role, _desc, _ctx in resolved_chars:
        metadata[f"char_{resolved_char.id}"] = True

    collection.upsert(
        ids=[scene_id],
        documents=[scene_text],
        metadatas=[metadata],
    )
