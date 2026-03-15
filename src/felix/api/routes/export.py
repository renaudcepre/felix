from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from felix.api.models import FullExport
from felix.db import repository

router = APIRouter(prefix="/api", tags=["export"])


@router.get("/export", response_model=FullExport)
async def export_all(request: Request) -> FullExport:
    db = request.app.state.db
    return FullExport(
        exported_at=datetime.now(timezone.utc),
        characters=await repository.list_all_characters_full(db),
        locations=await repository.list_all_locations(db),
        scenes=await repository.list_all_scenes_full(db),
        timeline_events=await repository.list_all_timeline_events(db),
        character_events=await repository.list_all_character_events(db),
        character_relations=await repository.list_all_character_relations(db),
        character_fragments=await repository.list_all_character_fragments(db),
        issues=await repository.list_issues(db),
    )
