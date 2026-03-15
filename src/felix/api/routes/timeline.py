from __future__ import annotations

from fastapi import APIRouter

from felix.api.deps import DB
from felix.api.models import TimelineEvent
from felix.db.repository import get_timeline_rows

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


@router.get("")
async def list_timeline(db: DB, era: str | None = None) -> list[TimelineEvent]:
    rows = await get_timeline_rows(db, era=era)
    return [TimelineEvent(**row) for row in rows]
