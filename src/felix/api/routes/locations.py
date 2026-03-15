from __future__ import annotations

from fastapi import APIRouter, HTTPException

from felix.api.deps import DB
from felix.api.models import LocationDetail, LocationSummary, SceneSummary
from felix.db.repository import get_location_detail, list_all_locations

router = APIRouter(prefix="/api/locations", tags=["locations"])


@router.get("")
async def list_locations(db: DB) -> list[LocationSummary]:
    rows = await list_all_locations(db)
    return [
        LocationSummary(id=row["id"], name=row["name"], era=row.get("era"))
        for row in rows
    ]


@router.get("/{loc_id}")
async def get_location(loc_id: str, db: DB) -> LocationDetail:
    data = await get_location_detail(db, loc_id)
    if not data:
        raise HTTPException(status_code=404, detail="Location not found")

    scenes = [
        SceneSummary(
            id=s["id"],
            filename=s["filename"],
            title=s.get("title"),
            era=s.get("era"),
            date=s.get("date"),
        )
        for s in data["scenes"]
    ]

    return LocationDetail(
        id=data["id"],
        name=data["name"],
        era=data.get("era"),
        description=data.get("description"),
        address=data.get("address"),
        scenes=scenes,
    )
