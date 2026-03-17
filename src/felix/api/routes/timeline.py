from __future__ import annotations

from fastapi import APIRouter

from felix.api.deps import Neo4jDriver
from felix.api.models import TimelineEvent
from felix.graph.repository import get_timeline_rows

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


@router.get("")
async def list_timeline(driver: Neo4jDriver, era: str | None = None) -> list[TimelineEvent]:
    rows = await get_timeline_rows(driver, era=era)
    return [TimelineEvent(**row) for row in rows]
