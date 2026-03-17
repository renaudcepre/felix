from __future__ import annotations

from fastapi import APIRouter, HTTPException

from felix.api.deps import Neo4jDriver
from felix.api.models import CharacterDetail, CharacterSummary, Relation
from felix.graph.repository import (
    get_character_profile,
    get_character_relations,
    list_all_characters,
)

router = APIRouter(prefix="/api/characters", tags=["characters"])


@router.get("")
async def list_characters(driver: Neo4jDriver) -> list[CharacterSummary]:
    rows = await list_all_characters(driver)
    return [
        CharacterSummary(id=row["id"], name=row["name"], era=row["era"])
        for row in rows
    ]


@router.get("/{char_id}")
async def get_character(char_id: str, driver: Neo4jDriver) -> CharacterDetail:
    row = await get_character_profile(driver, char_id)
    if not row:
        raise HTTPException(status_code=404, detail="Character not found")

    rels = await get_character_relations(driver, char_id)
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
        aliases=row.get("aliases"),
        era=row.get("era"),
        age=row.get("age"),
        physical=row.get("physical"),
        background=row.get("background"),
        arc=row.get("arc"),
        traits=row.get("traits"),
        status=row.get("status"),
        relations=relations,
    )
