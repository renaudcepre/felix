"""Neo4j repository — Scene CRUD, stems, and chunks."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncManagedTransaction

    from felix.graph.repositories._types import (
        SceneFullRow,
        SceneSummaryRow,
        SceneWithSummaryRow,
    )


async def upsert_scene(driver: AsyncDriver, scene: dict[str, Any]) -> None:
    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MERGE (s:Scene {id: $id})
            SET s.filename = $filename, s.title = $title, s.summary = $summary,
                s.era = $era, s.date = $date, s.raw_text = $raw_text
            """,
            id=scene["id"],
            filename=scene["filename"],
            title=scene["title"],
            summary=scene["summary"],
            era=scene["era"],
            date=scene["date"],
            raw_text=scene["raw_text"],
        )
        await tx.run(
            "MATCH (s:Scene {id: $sid})-[r:AT_LOCATION]->() DELETE r",
            sid=scene["id"],
        )
        if scene.get("location_id"):
            await tx.run(
                """
                MATCH (s:Scene {id: $sid}), (l:Location {id: $lid})
                MERGE (s)-[:AT_LOCATION]->(l)
                """,
                sid=scene["id"],
                lid=scene["location_id"],
            )

    async with driver.session() as session:
        await session.execute_write(_write)


async def list_scenes(driver: AsyncDriver) -> list[SceneSummaryRow]:
    async def _read(tx: AsyncManagedTransaction) -> list[SceneSummaryRow]:
        result = await tx.run(
            """
            MATCH (s:Scene)
            RETURN s.id AS id, s.filename AS filename, s.title AS title,
                   s.era AS era, s.date AS date
            ORDER BY s.filename
            """
        )
        return cast("list[SceneSummaryRow]", [dict(r) for r in await result.data()])

    async with driver.session() as session:
        return await session.execute_read(_read)


async def get_scene_summaries_by_ids(
    driver: AsyncDriver,
    scene_ids: list[str],
) -> list[SceneWithSummaryRow]:
    if not scene_ids:
        return []

    async def _read(tx: AsyncManagedTransaction) -> list[SceneWithSummaryRow]:
        result = await tx.run(
            """
            MATCH (s:Scene)
            WHERE s.id IN $ids
            OPTIONAL MATCH (s)-[:AT_LOCATION]->(l:Location)
            RETURN s.id AS id, s.title AS title, s.summary AS summary,
                   s.era AS era, s.date AS date, l.id AS location_id
            """,
            ids=scene_ids,
        )
        return cast("list[SceneWithSummaryRow]", [dict(r) for r in await result.data()])

    async with driver.session() as session:
        return await session.execute_read(_read)


async def list_all_scenes_full(driver: AsyncDriver) -> list[SceneFullRow]:
    async def _read(tx: AsyncManagedTransaction) -> list[SceneFullRow]:
        result = await tx.run(
            "MATCH (s:Scene) RETURN s ORDER BY s.filename"
        )
        return cast("list[SceneFullRow]", [dict(r["s"]) for r in await result.data()])

    async with driver.session() as session:
        return await session.execute_read(_read)


async def get_scene_ids_for_stems(
    driver: AsyncDriver, stems: list[str]
) -> list[str]:
    """Return all Scene IDs whose id starts with 'scene-{stem}' for idempotent re-import."""
    if not stems:
        return []

    async def _read(tx: AsyncManagedTransaction) -> list[str]:
        result = await tx.run(
            """
            MATCH (s:Scene)
            WHERE any(stem IN $stems WHERE s.id STARTS WITH ('scene-' + stem))
            RETURN s.id AS id
            """,
            stems=stems,
        )
        return [r["id"] for r in await result.data()]

    async with driver.session() as session:
        return await session.execute_read(_read)


async def count_scenes_for_stem(driver: AsyncDriver, stem: str) -> int:
    """Return the number of Scene nodes whose id starts with 'scene-{stem}'."""
    async def _read(tx: AsyncManagedTransaction) -> int:
        result = await tx.run(
            "MATCH (s:Scene) WHERE s.id STARTS WITH $prefix RETURN count(s) AS n",
            prefix=f"scene-{stem}",
        )
        record = await result.single()
        return record["n"] if record else 0

    async with driver.session() as session:
        return await session.execute_read(_read)


async def count_next_chunk_links_for_stem(driver: AsyncDriver, stem: str) -> int:
    """Return the number of NEXT_CHUNK relationships for scenes matching 'scene-{stem}'."""
    async def _read(tx: AsyncManagedTransaction) -> int:
        result = await tx.run(
            """
            MATCH (s1:Scene)-[:NEXT_CHUNK]->(s2:Scene)
            WHERE s1.id STARTS WITH $prefix
            RETURN count(*) AS n
            """,
            prefix=f"scene-{stem}",
        )
        record = await result.single()
        return record["n"] if record else 0

    async with driver.session() as session:
        return await session.execute_read(_read)
