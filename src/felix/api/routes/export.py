from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from felix.api.deps import Neo4jDriver
from felix.api.models import FullExport
from felix.graph.repositories.characters import (
    list_all_character_fragments,
    list_all_character_relations,
    list_all_characters_full,
)
from felix.graph.repositories.beats import list_all_narrative_beats
from felix.graph.repositories.issues import list_issues
from felix.graph.repositories.locations import list_all_locations
from felix.graph.repositories.scenes import list_all_scenes_full
from felix.graph.repositories.timeline import list_all_character_events, list_all_timeline_events

router = APIRouter(prefix="/api", tags=["export"])


@router.get("/export", response_model=FullExport)
async def export_all(driver: Neo4jDriver) -> FullExport:
    return FullExport(
        exported_at=datetime.now(timezone.utc),
        characters=await list_all_characters_full(driver),
        locations=await list_all_locations(driver),
        scenes=await list_all_scenes_full(driver),
        timeline_events=await list_all_timeline_events(driver),
        character_events=await list_all_character_events(driver),
        character_relations=await list_all_character_relations(driver),
        character_fragments=await list_all_character_fragments(driver),
        narrative_beats=await list_all_narrative_beats(driver),
        issues=await list_issues(driver),
    )
