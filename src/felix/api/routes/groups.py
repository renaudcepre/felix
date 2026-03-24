from __future__ import annotations

from fastapi import APIRouter, HTTPException

from felix.api.deps import Neo4jDriver
from felix.api.models import GroupCreate, GroupDetail, GroupMember, GroupSummary
from felix.graph.repositories.groups import (
    create_member_of,
    get_group_detail,
    list_all_groups,
    remove_member_of,
    upsert_group_minimal,
)
from felix.ingest.utils import normalize

router = APIRouter(prefix="/api/groups", tags=["groups"])


@router.get("")
async def list_groups(driver: Neo4jDriver) -> list[GroupSummary]:
    rows = await list_all_groups(driver)
    return [GroupSummary(id=row["id"], name=row["name"]) for row in rows]


@router.post("", status_code=201)
async def create_group(body: GroupCreate, driver: Neo4jDriver) -> GroupSummary:
    slug = "-".join(normalize(body.name).split())
    group = {"id": slug, "name": body.name, "era": body.era}
    await upsert_group_minimal(driver, group)
    return GroupSummary(id=slug, name=body.name)


@router.get("/{group_id}")
async def get_group(group_id: str, driver: Neo4jDriver) -> GroupDetail:
    data = await get_group_detail(driver, group_id)
    if not data:
        raise HTTPException(status_code=404, detail="Group not found")

    members = [
        GroupMember(id=m["id"], name=m["name"], era=m.get("era", ""))
        for m in data.get("members", [])
    ]

    return GroupDetail(
        id=data["id"],
        name=data["name"],
        era=data.get("era"),
        members=members,
    )


@router.put("/{group_id}/members/{char_id}", status_code=204)
async def add_member(group_id: str, char_id: str, driver: Neo4jDriver) -> None:
    await create_member_of(driver, char_id, group_id)


@router.delete("/{group_id}/members/{char_id}", status_code=204)
async def remove_member(group_id: str, char_id: str, driver: Neo4jDriver) -> None:
    deleted = await remove_member_of(driver, char_id, group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Membership not found")
