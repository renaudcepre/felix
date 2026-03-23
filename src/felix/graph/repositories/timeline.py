"""Neo4j repository — TimelineEvent and CharacterEvent."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncManagedTransaction


async def upsert_timeline_event(
    driver: AsyncDriver, evt: dict[str, Any]
) -> None:
    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MERGE (e:TimelineEvent {id: $id})
            SET e.date = $date, e.era = $era, e.title = $title,
                e.description = $description
            """,
            id=evt["id"],
            date=evt["date"],
            era=evt["era"],
            title=evt["title"],
            description=evt.get("description"),
        )
        if evt.get("location_id"):
            await tx.run(
                """
                MATCH (e:TimelineEvent {id: $eid}), (l:Location {id: $lid})
                MERGE (e)-[:AT_LOCATION]->(l)
                """,
                eid=evt["id"],
                lid=evt["location_id"],
            )
        if evt.get("scene_id"):
            await tx.run(
                """
                MATCH (e:TimelineEvent {id: $eid}), (s:Scene {id: $sid})
                MERGE (e)-[:FROM_SCENE]->(s)
                """,
                eid=evt["id"],
                sid=evt["scene_id"],
            )

    async with driver.session() as session:
        await session.execute_write(_write)


async def upsert_character_event(
    driver: AsyncDriver, character_id: str, event_id: str, role: str
) -> None:
    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MATCH (c:Character {id: $cid}), (e:TimelineEvent {id: $eid})
            MERGE (c)-[r:PARTICIPATES_IN]->(e)
            SET r.role = $role
            """,
            cid=character_id,
            eid=event_id,
            role=role,
        )

    async with driver.session() as session:
        await session.execute_write(_write)


async def get_timeline_rows(
    driver: AsyncDriver,
    *,
    era: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    location: str | None = None,
) -> list[dict[str, Any]]:
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(
            """
            MATCH (e:TimelineEvent)
            WHERE ($era IS NULL OR e.era = $era)
              AND ($date_from IS NULL OR e.date >= $date_from)
              AND ($date_to   IS NULL OR e.date <= $date_to)
            OPTIONAL MATCH (e)-[:AT_LOCATION]->(l:Location)
            WITH e, l
            WHERE $location IS NULL
               OR (l IS NOT NULL AND toLower(l.name) CONTAINS toLower($location))
            OPTIONAL MATCH (c:Character)-[:PARTICIPATES_IN]->(e)
            RETURN e.id AS id, e.date AS date, e.era AS era,
                   e.title AS title, e.description AS description,
                   l.id AS location_id, l.name AS location_name,
                   collect({id: c.id, name: c.name}) AS characters
            ORDER BY e.date
            """,
            era=era,
            date_from=date_from,
            date_to=date_to,
            location=location,
        )
        rows = []
        for evt in await result.data():
            characters_detail = [
                {"id": c["id"], "name": c["name"]}
                for c in evt["characters"]
                if c["id"] is not None
            ]
            rows.append({
                "id": evt["id"],
                "date": evt["date"],
                "era": evt["era"],
                "title": evt["title"],
                "description": evt["description"] or "",
                "location": evt["location_name"] or "",
                "location_id": evt["location_id"],
                "characters": ", ".join(c["name"] for c in characters_detail),
                "characters_detail": characters_detail,
            })
        return rows

    async with driver.session() as session:
        return await session.execute_read(_read)


async def list_all_timeline_events(driver: AsyncDriver) -> list[dict[str, Any]]:
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(
            "MATCH (e:TimelineEvent) RETURN e ORDER BY e.date"
        )
        return [dict(r["e"]) for r in await result.data()]

    async with driver.session() as session:
        return await session.execute_read(_read)


async def list_all_character_events(driver: AsyncDriver) -> list[dict[str, Any]]:
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(
            """
            MATCH (c:Character)-[r:PARTICIPATES_IN]->(e:TimelineEvent)
            RETURN c.id AS character_id, e.id AS event_id, r.role AS role
            """
        )
        return [dict(r) for r in await result.data()]

    async with driver.session() as session:
        return await session.execute_read(_read)
