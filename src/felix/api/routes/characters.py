from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from felix.api.deps import BaseUrl, ModelName, Neo4jDriver
from felix.api.models import (
    CharacterCreate,
    CharacterDetail,
    CharacterProfileUpdate,
    CharacterSummary,
    Relation,
    RelationUpsert,
)
from felix.ingest.entity_checker import check_character_consistency
from felix.ingest.models import ConsistencyReport
from felix.graph.repositories.characters import (
    delete_character_relation,
    get_character_profile,
    get_character_relations,
    list_all_characters,
    overwrite_character_profile_fields,
    upsert_character_minimal,
    upsert_character_relation,
)
from felix.ingest.resolver import slugify

router = APIRouter(prefix="/api/characters", tags=["characters"])


@router.get("")
async def list_characters(driver: Neo4jDriver) -> list[CharacterSummary]:
    rows = await list_all_characters(driver)
    return [
        CharacterSummary(id=row["id"], name=row["name"], era=row["era"])
        for row in rows
    ]


@router.post("", status_code=201)
async def create_character(body: CharacterCreate, driver: Neo4jDriver) -> CharacterSummary:
    char_id = slugify(body.name)
    existing = await get_character_profile(driver, char_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Character {body.name} already exists")
    await upsert_character_minimal(driver, {"id": char_id, "name": body.name, "era": body.era})
    return CharacterSummary(id=char_id, name=body.name, era=body.era)


@router.get("/{char_id}")
async def get_character(char_id: str, driver: Neo4jDriver) -> CharacterDetail:
    return await _build_character_detail(driver, char_id)


@router.patch("/{char_id}")
async def update_character(
    char_id: str, body: CharacterProfileUpdate, driver: Neo4jDriver
) -> CharacterDetail:
    fields = {k: v for k, v in body.model_dump().items() if k in body.model_fields_set}
    if fields:
        found = await overwrite_character_profile_fields(driver, char_id, fields)
        if not found:
            raise HTTPException(status_code=404, detail="Character not found")
    return await _build_character_detail(driver, char_id)


@router.put("/{char_id_a}/relations/{char_id_b}")
async def upsert_relation(
    char_id_a: str, char_id_b: str, body: RelationUpsert, driver: Neo4jDriver
) -> Relation:
    # Vérifier que les 2 personnages existent
    for cid in (char_id_a, char_id_b):
        if not await get_character_profile(driver, cid):
            raise HTTPException(status_code=404, detail=f"Character {cid} not found")

    await upsert_character_relation(
        driver, char_id_a, char_id_b,
        relation_type=body.relation_type,
        description=body.description,
        era=body.era,
    )

    # Retourner la relation du point de vue de char_id_a
    other = await get_character_profile(driver, char_id_b)
    return Relation(
        relation_type=body.relation_type,
        other_name=other["name"],
        era=body.era,
        description=body.description,
    )


@router.delete("/{char_id_a}/relations/{char_id_b}", status_code=204)
async def delete_relation_endpoint(
    char_id_a: str,
    char_id_b: str,
    driver: Neo4jDriver,
    relation_type: str = Query(...),
) -> None:
    deleted = await delete_character_relation(driver, char_id_a, char_id_b, relation_type)
    if not deleted:
        raise HTTPException(status_code=404, detail="Relation not found")


@router.post("/{char_id}/check-consistency")
async def check_consistency(
    char_id: str,
    body: CharacterProfileUpdate,
    driver: Neo4jDriver,
    model_name: ModelName,
    base_url: BaseUrl,
) -> ConsistencyReport:
    profile = await get_character_profile(driver, char_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Character not found")

    fields = {k: v for k, v in body.model_dump().items() if k in body.model_fields_set}
    if not fields:
        return ConsistencyReport(issues=[])

    # Only check fields that actually differ from the current profile
    # Normalize: strip whitespace, treat empty strings as None
    def _norm(val: str | None) -> str | None:
        return val.strip() or None if isinstance(val, str) else val

    changed = {k: v for k, v in fields.items() if _norm(v) != _norm(profile.get(k))}
    if not changed:
        return ConsistencyReport(issues=[])

    return await check_character_consistency(
        driver, char_id, changed, model_name, base_url
    )


async def _build_character_detail(driver: Neo4jDriver, char_id: str) -> CharacterDetail:
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
