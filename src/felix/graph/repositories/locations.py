"""Neo4j repository — Location CRUD and aliases."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncManagedTransaction


async def upsert_location_minimal(
    driver: AsyncDriver, loc: dict[str, Any]
) -> None:
    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MERGE (l:Location {id: $id})
            ON CREATE SET l.name = $name, l.description = $description
            """,
            id=loc["id"],
            name=loc["name"],
            description=loc.get("description"),
        )

    async with driver.session() as session:
        await session.execute_write(_write)


async def list_all_locations(driver: AsyncDriver) -> list[dict[str, Any]]:
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(
            "MATCH (l:Location) RETURN l ORDER BY l.era, l.name"
        )
        return [dict(r["l"]) for r in await result.data()]

    async with driver.session() as session:
        return await session.execute_read(_read)


async def add_location_alias(driver: AsyncDriver, loc_id: str, alias: str) -> None:
    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MATCH (l:Location {id: $id})
            SET l.aliases = CASE
                WHEN $alias IN coalesce(l.aliases, []) THEN coalesce(l.aliases, [])
                ELSE coalesce(l.aliases, []) + [$alias]
            END
            """,
            id=loc_id,
            alias=alias,
        )

    async with driver.session() as session:
        await session.execute_write(_write)


async def get_location_detail(
    driver: AsyncDriver, loc_id: str
) -> dict[str, Any] | None:
    async def _read(tx: AsyncManagedTransaction) -> dict[str, Any] | None:
        result = await tx.run(
            "MATCH (l:Location {id: $id}) RETURN l", id=loc_id
        )
        record = await result.single()
        if not record:
            return None
        data = dict(record["l"])

        scenes_result = await tx.run(
            """
            MATCH (s:Scene)-[:AT_LOCATION]->(l:Location {id: $id})
            RETURN s.id AS id, s.filename AS filename, s.title AS title,
                   s.era AS era, s.date AS date
            ORDER BY s.filename
            """,
            id=loc_id,
        )
        data["scenes"] = [dict(r) for r in await scenes_result.data()]
        return data

    async with driver.session() as session:
        return await session.execute_read(_read)
