"""Neo4j repository — Group CRUD and MEMBER_OF."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncManagedTransaction


async def upsert_group_minimal(driver: AsyncDriver, group: dict[str, Any]) -> None:
    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MERGE (g:Group {id: $id})
            ON CREATE SET g.name = $name, g.era = $era
            """,
            id=group["id"],
            name=group["name"],
            era=group.get("era"),
        )

    async with driver.session() as session:
        await session.execute_write(_write)


async def upsert_group_in_scene(  # noqa: PLR0913
    driver: AsyncDriver,
    group_id: str,
    scene_id: str,
    role: str | None,
    description: str | None,
    context: str | None = None,
) -> None:
    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MATCH (g:Group {id: $gid}), (s:Scene {id: $sid})
            MERGE (g)-[r:PRESENT_IN]->(s)
            SET r.role = $role, r.description = $description, r.context = $context
            """,
            gid=group_id,
            sid=scene_id,
            role=role or "",
            description=description,
            context=context,
        )

    async with driver.session() as session:
        await session.execute_write(_write)


async def list_all_groups(driver: AsyncDriver) -> list[dict[str, Any]]:
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(
            "MATCH (g:Group) RETURN g.id AS id, g.name AS name ORDER BY g.name"
        )
        return [dict(r) for r in await result.data()]

    _notif = logging.getLogger("neo4j.notifications")
    _prev = _notif.level
    _notif.setLevel(logging.ERROR)
    try:
        async with driver.session() as session:
            return await session.execute_read(_read)
    finally:
        _notif.setLevel(_prev)


async def create_member_of(driver: AsyncDriver, char_id: str, group_id: str) -> None:
    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MATCH (c:Character {id: $cid}), (g:Group {id: $gid})
            MERGE (c)-[:MEMBER_OF]->(g)
            """,
            cid=char_id,
            gid=group_id,
        )

    async with driver.session() as session:
        await session.execute_write(_write)
