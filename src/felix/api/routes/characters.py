from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from felix.api.models import CharacterDetail, CharacterSummary, Relation
from felix.db.queries import (
    get_character_profile,
    get_character_relations,
    list_all_characters,
)

router = APIRouter(prefix="/api/characters", tags=["characters"])


@router.get("")
async def list_characters(request: Request) -> list[CharacterSummary]:
    db = request.app.state.db
    rows = await list_all_characters(db)
    return [
        CharacterSummary(id=row["id"], name=row["name"], era=row["era"])
        for row in rows
    ]


@router.get("/{char_id}")
async def get_character(char_id: str, request: Request) -> CharacterDetail:
    db = request.app.state.db
    row = await get_character_profile(db, char_id)
    if not row:
        raise HTTPException(status_code=404, detail="Character not found")

    rels = await get_character_relations(db, char_id)
    relations = [
        Relation(
            relation_type=r["relation_type"],
            other_name=r["other_name"],
            era=r["era"],
            description=r["description"],
        )
        for r in rels
    ]

    return CharacterDetail(
        id=row["id"],
        name=row["name"],
        aliases=row["aliases"],
        era=row["era"],
        age=row["age"],
        physical=row["physical"],
        background=row["background"],
        arc=row["arc"],
        traits=row["traits"],
        status=row["status"],
        relations=relations,
    )
