"""Graph write operations — Neo4j async version."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncManagedTransaction


async def delete_scenes(driver: AsyncDriver, scene_ids: list[str]) -> None:
    """Remove scene nodes and their edges (idempotent re-import)."""
    if not scene_ids:
        return

    async def _tx(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            "MATCH (s:Scene) WHERE s.id IN $ids DETACH DELETE s",
            ids=scene_ids,
        )

    async with driver.session() as session:
        await session.execute_write(_tx)


async def write_scene(driver: AsyncDriver, scene_summary: dict[str, Any]) -> None:
    """Write Character, Scene, Location nodes and edges atomically."""
    scene_id = scene_summary["scene_id"]
    loc = scene_summary["location"]
    characters = scene_summary.get("characters", [])

    async def _tx(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            "MERGE (l:Location {id: $id}) ON CREATE SET l.name = $name",
            id=loc["id"],
            name=loc["name"],
        )
        await tx.run(
            """
            MERGE (s:Scene {id: $id})
            SET s.title = $title, s.date = $date, s.era = $era
            """,
            id=scene_id,
            title=scene_summary.get("title"),
            date=scene_summary.get("date"),
            era=scene_summary.get("era"),
        )
        await tx.run(
            """
            MATCH (s:Scene {id: $sid}), (l:Location {id: $lid})
            MERGE (s)-[:AT_LOCATION]->(l)
            """,
            sid=scene_id,
            lid=loc["id"],
        )
        for char in characters:
            await tx.run(
                "MERGE (c:Character {id: $id}) ON CREATE SET c.name = $name",
                id=char["id"],
                name=char["name"],
            )
            await tx.run(
                """
                MATCH (c:Character {id: $cid}), (s:Scene {id: $sid})
                MERGE (c)-[r:PRESENT_IN {role: $role}]->(s)
                """,
                cid=char["id"],
                sid=scene_id,
                role=char.get("role", ""),
            )

        for group in scene_summary.get("groups", []):
            await tx.run(
                "MERGE (g:Group {id: $id}) ON CREATE SET g.name = $name",
                id=group["id"],
                name=group["name"],
            )
            await tx.run(
                """
                MATCH (g:Group {id: $gid}), (s:Scene {id: $sid})
                MERGE (g)-[r:PRESENT_IN {role: $role}]->(s)
                """,
                gid=group["id"],
                sid=scene_id,
                role=group.get("role", ""),
            )

    async with driver.session() as session:
        await session.execute_write(_tx)


async def link_next_chunk(driver: AsyncDriver, from_id: str, to_id: str) -> None:
    """Create (s1)-[:NEXT_CHUNK]->(s2) between two consecutive scene chunks."""
    async def _tx(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MATCH (s1:Scene {id: $from_id}), (s2:Scene {id: $to_id})
            MERGE (s1)-[:NEXT_CHUNK]->(s2)
            """,
            from_id=from_id,
            to_id=to_id,
        )

    async with driver.session() as session:
        await session.execute_write(_tx)
