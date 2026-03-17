from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from felix.api.deps import Neo4jDriver
from felix.api.models import FullExport
from felix.graph import repository

router = APIRouter(prefix="/api", tags=["export"])


@router.get("/export", response_model=FullExport)
async def export_all(driver: Neo4jDriver) -> FullExport:
    return FullExport(
        exported_at=datetime.now(timezone.utc),
        characters=await repository.list_all_characters_full(driver),
        locations=await repository.list_all_locations(driver),
        scenes=await repository.list_all_scenes_full(driver),
        timeline_events=await repository.list_all_timeline_events(driver),
        character_events=await repository.list_all_character_events(driver),
        character_relations=await repository.list_all_character_relations(driver),
        character_fragments=await repository.list_all_character_fragments(driver),
        issues=await repository.list_issues(driver),
    )
