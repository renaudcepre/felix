"""Neo4j repository — NarrativeBeat CRUD."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncManagedTransaction


async def create_narrative_beat(
    driver: AsyncDriver, beat_id: str, action: str, scene_id: str
) -> None:
    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MERGE (b:NarrativeBeat {id: $id})
            SET b.action = $action
            WITH b
            MATCH (s:Scene {id: $scene_id})
            MERGE (b)-[:OCCURS_IN]->(s)
            """,
            id=beat_id,
            action=action,
            scene_id=scene_id,
        )

    async with driver.session() as session:
        await session.execute_write(_write)


async def link_beat_character(
    driver: AsyncDriver, beat_id: str, char_id: str, role: str
) -> None:
    async def _write(tx: AsyncManagedTransaction) -> None:
        if role == "subject":
            await tx.run(
                """
                MATCH (b:NarrativeBeat {id: $beat_id}), (c:Character {id: $char_id})
                MERGE (c)-[:SUBJECT_OF]->(b)
                """,
                beat_id=beat_id,
                char_id=char_id,
            )
        else:
            await tx.run(
                """
                MATCH (b:NarrativeBeat {id: $beat_id}), (c:Character {id: $char_id})
                MERGE (b)-[:AFFECTS]->(c)
                """,
                beat_id=beat_id,
                char_id=char_id,
            )

    async with driver.session() as session:
        await session.execute_write(_write)


async def list_all_narrative_beats(driver: AsyncDriver) -> list[dict[str, Any]]:
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(
            """
            MATCH (b:NarrativeBeat)-[:OCCURS_IN]->(s:Scene)
            OPTIONAL MATCH (subject:Character)-[:SUBJECT_OF]->(b)
            OPTIONAL MATCH (b)-[:AFFECTS]->(object:Character)
            RETURN b.id AS id, b.action AS action, s.id AS scene_id,
                   subject.id AS subject_id, subject.name AS subject_name,
                   object.id AS object_id, object.name AS object_name
            ORDER BY s.id, b.id
            """
        )
        return [dict(r) for r in await result.data()]

    async with driver.session() as session:
        return await session.execute_read(_read)
