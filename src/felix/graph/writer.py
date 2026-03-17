"""Graph write operations — Neo4j async version."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver


async def delete_scenes(driver: AsyncDriver, scene_ids: list[str]) -> None:
    """Remove scene nodes and their edges (idempotent re-import)."""
    if not scene_ids:
        return
    async with driver.session() as session:
        await session.run(
            """
            MATCH (s:Scene) WHERE s.id IN $ids
            DETACH DELETE s
            """,
            ids=scene_ids,
        )


async def write_scene(driver: AsyncDriver, scene_summary: dict[str, Any]) -> None:
    """Write Character, Scene, Location nodes and edges to the graph."""
    scene_id = scene_summary["scene_id"]
    loc = scene_summary["location"]

    async with driver.session() as session:
        await session.run(
            "MERGE (l:Location {id: $id}) ON CREATE SET l.name = $name",
            id=loc["id"],
            name=loc["name"],
        )
        await session.run(
            """
            MERGE (s:Scene {id: $id})
            SET s.title = $title, s.date = $date, s.era = $era
            """,
            id=scene_id,
            title=scene_summary.get("title"),
            date=scene_summary.get("date"),
            era=scene_summary.get("era"),
        )
        await session.run(
            """
            MATCH (s:Scene {id: $sid}), (l:Location {id: $lid})
            MERGE (s)-[:AT_LOCATION]->(l)
            """,
            sid=scene_id,
            lid=loc["id"],
        )

        for char in scene_summary.get("characters", []):
            await session.run(
                "MERGE (c:Character {id: $id}) ON CREATE SET c.name = $name",
                id=char["id"],
                name=char["name"],
            )
            await session.run(
                """
                MATCH (c:Character {id: $cid}), (s:Scene {id: $sid})
                MERGE (c)-[r:PRESENT_IN {role: $role}]->(s)
                """,
                cid=char["id"],
                sid=scene_id,
                role=char.get("role", ""),
            )
