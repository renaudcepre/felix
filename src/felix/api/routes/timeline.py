from __future__ import annotations

from fastapi import APIRouter, Request

from felix.api.models import TimelineEvent
from felix.db.queries import get_timeline_rows

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


@router.get("")
async def list_timeline(
    request: Request, era: str | None = None
) -> list[TimelineEvent]:
    db = request.app.state.db
    rows = await get_timeline_rows(db, era=era)
    return [TimelineEvent(**row) for row in rows]
