"""Neo4j repository — async Cypher equivalents of the former aiosqlite repository."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------


async def list_all_characters(driver: AsyncDriver) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Character) RETURN c.id AS id, c.name AS name, c.era AS era"
            " ORDER BY c.era, c.name"
        )
        return [dict(r) for r in await result.data()]


async def get_character_profile(
    driver: AsyncDriver, char_id: str
) -> dict[str, Any] | None:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Character {id: $id}) RETURN c", id=char_id
        )
        record = await result.single()
        if not record:
            return None
        node = dict(record["c"])
        # aliases is stored natively as LIST<STRING>; keep as-is
        return node


async def get_character_relations(
    driver: AsyncDriver, char_id: str
) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (c:Character {id: $id})-[r:RELATED_TO]-(other:Character)
            RETURN r.relation_type AS relation_type,
                   r.description   AS description,
                   r.era           AS era,
                   other.name      AS other_name
            """,
            id=char_id,
        )
        return [dict(r) for r in await result.data()]


async def list_all_characters_full(driver: AsyncDriver) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Character) RETURN c ORDER BY c.era, c.name"
        )
        return [dict(r["c"]) for r in await result.data()]


async def upsert_character_minimal(
    driver: AsyncDriver, char: dict[str, Any]
) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (c:Character {id: $id})
            ON CREATE SET c.name = $name, c.era = $era
            """,
            id=char["id"],
            name=char["name"],
            era=char.get("era"),
        )


async def update_character_profile(
    driver: AsyncDriver, char_id: str, profile: dict[str, str | None]
) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (c:Character {id: $id})
            SET c.age        = CASE WHEN c.age IS NULL THEN $age ELSE c.age END,
                c.physical   = CASE WHEN c.physical IS NULL THEN $physical ELSE c.physical END,
                c.background = CASE WHEN c.background IS NULL THEN $background ELSE c.background END,
                c.arc        = CASE WHEN c.arc IS NULL THEN $arc ELSE c.arc END,
                c.traits     = CASE WHEN c.traits IS NULL THEN $traits ELSE c.traits END
            """,
            id=char_id,
            age=profile.get("age"),
            physical=profile.get("physical"),
            background=profile.get("background"),
            arc=profile.get("arc"),
            traits=profile.get("traits"),
        )


def _nullify_empty(v: str | None) -> str | None:
    return v if v and v.strip() else None


async def patch_character_profile_fields(
    driver: AsyncDriver, char_id: str, profile: dict[str, str | None]
) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (c:Character {id: $id})
            SET c.age      = CASE WHEN $age IS NOT NULL THEN $age ELSE c.age END,
                c.physical = CASE WHEN $physical IS NOT NULL THEN $physical ELSE c.physical END,
                c.background = CASE
                    WHEN $background IS NULL THEN c.background
                    WHEN c.background IS NULL THEN $background
                    ELSE c.background + ' | ' + $background END,
                c.arc = CASE
                    WHEN $arc IS NULL THEN c.arc
                    WHEN c.arc IS NULL THEN $arc
                    ELSE c.arc + ' | ' + $arc END,
                c.traits = CASE
                    WHEN $traits IS NULL THEN c.traits
                    WHEN c.traits IS NULL THEN $traits
                    ELSE c.traits + ' | ' + $traits END
            """,
            id=char_id,
            age=_nullify_empty(profile.get("age")),
            physical=_nullify_empty(profile.get("physical")),
            background=_nullify_empty(profile.get("background")),
            arc=_nullify_empty(profile.get("arc")),
            traits=_nullify_empty(profile.get("traits")),
        )


# ---------------------------------------------------------------------------
# Character relations
# ---------------------------------------------------------------------------


async def get_relation_types_for_pair(
    driver: AsyncDriver,
    char_id_a: str,
    char_id_b: str,
) -> list[str]:
    a, b = sorted([char_id_a, char_id_b])
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:Character {id: $a})-[r:RELATED_TO]-(b:Character {id: $b})
            RETURN r.relation_type AS relation_type
            """,
            a=a,
            b=b,
        )
        return [r["relation_type"] for r in await result.data()]


async def upsert_character_relation(
    driver: AsyncDriver,
    char_id_a: str,
    char_id_b: str,
    relation_type: str,
    description: str | None = None,
    era: str | None = None,
) -> None:
    a, b = sorted([char_id_a, char_id_b])
    async with driver.session() as session:
        await session.run(
            """
            MATCH (a:Character {id: $a}), (b:Character {id: $b})
            MERGE (a)-[r:RELATED_TO {relation_type: $relation_type}]-(b)
            SET r.description = $description, r.era = $era
            """,
            a=a,
            b=b,
            relation_type=relation_type,
            description=description,
            era=era,
        )


async def list_all_character_relations(driver: AsyncDriver) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:Character)-[r:RELATED_TO]->(b:Character)
            RETURN a.id AS character_id_a, b.id AS character_id_b,
                   r.relation_type AS relation_type,
                   r.description AS description, r.era AS era
            """
        )
        return [dict(r) for r in await result.data()]


# ---------------------------------------------------------------------------
# Character fragments (PRESENT_IN)
# ---------------------------------------------------------------------------


async def upsert_character_fragment(
    driver: AsyncDriver,
    character_id: str,
    scene_id: str,
    role: str | None,
    description: str | None,
) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (c:Character {id: $cid}), (s:Scene {id: $sid})
            MERGE (c)-[r:PRESENT_IN {role: $role}]->(s)
            SET r.description = $description
            """,
            cid=character_id,
            sid=scene_id,
            role=role or "",
            description=description,
        )


async def get_character_fragments(
    driver: AsyncDriver, character_id: str
) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (c:Character {id: $cid})-[r:PRESENT_IN]->(s:Scene)
            RETURN s.id AS scene_id, r.role AS role, r.description AS description,
                   s.title AS scene_title
            ORDER BY s.filename
            """,
            cid=character_id,
        )
        return [dict(r) for r in await result.data()]


async def list_all_character_fragments(driver: AsyncDriver) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (c:Character)-[r:PRESENT_IN]->(s:Scene)
            RETURN c.id AS character_id, s.id AS scene_id,
                   r.role AS role, r.description AS description
            """
        )
        return [dict(r) for r in await result.data()]


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------


async def upsert_location_minimal(
    driver: AsyncDriver, loc: dict[str, Any]
) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (l:Location {id: $id})
            ON CREATE SET l.name = $name, l.description = $description
            """,
            id=loc["id"],
            name=loc["name"],
            description=loc.get("description"),
        )


async def list_all_locations(driver: AsyncDriver) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (l:Location) RETURN l ORDER BY l.era, l.name"
        )
        return [dict(r["l"]) for r in await result.data()]


async def get_location_detail(
    driver: AsyncDriver, loc_id: str
) -> dict[str, Any] | None:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (l:Location {id: $id}) RETURN l", id=loc_id
        )
        record = await result.single()
        if not record:
            return None
        data = dict(record["l"])

        scenes_result = await session.run(
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


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------


async def upsert_scene(driver: AsyncDriver, scene: dict[str, Any]) -> None:
    async with driver.session() as session:
        await session.run(
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
        if scene.get("location_id"):
            await session.run(
                """
                MATCH (s:Scene {id: $sid}), (l:Location {id: $lid})
                MERGE (s)-[:AT_LOCATION]->(l)
                """,
                sid=scene["id"],
                lid=scene["location_id"],
            )


async def list_scenes(driver: AsyncDriver) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (s:Scene)
            RETURN s.id AS id, s.filename AS filename, s.title AS title,
                   s.era AS era, s.date AS date
            ORDER BY s.filename
            """
        )
        return [dict(r) for r in await result.data()]


async def get_scene_summaries_by_ids(
    driver: AsyncDriver,
    scene_ids: list[str],
) -> list[dict[str, Any]]:
    if not scene_ids:
        return []
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (s:Scene)
            WHERE s.id IN $ids
            OPTIONAL MATCH (s)-[:AT_LOCATION]->(l:Location)
            RETURN s.id AS id, s.title AS title, s.summary AS summary,
                   s.era AS era, s.date AS date, l.id AS location_id
            """,
            ids=scene_ids,
        )
        return [dict(r) for r in await result.data()]


async def list_all_scenes_full(driver: AsyncDriver) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (s:Scene) RETURN s ORDER BY s.filename"
        )
        return [dict(r["s"]) for r in await result.data()]


# ---------------------------------------------------------------------------
# Timeline events
# ---------------------------------------------------------------------------


async def upsert_timeline_event(
    driver: AsyncDriver, evt: dict[str, Any]
) -> None:
    async with driver.session() as session:
        await session.run(
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
            await session.run(
                """
                MATCH (e:TimelineEvent {id: $eid}), (l:Location {id: $lid})
                MERGE (e)-[:AT_LOCATION]->(l)
                """,
                eid=evt["id"],
                lid=evt["location_id"],
            )
        if evt.get("scene_id"):
            await session.run(
                """
                MATCH (e:TimelineEvent {id: $eid}), (s:Scene {id: $sid})
                MERGE (e)-[:FROM_SCENE]->(s)
                """,
                eid=evt["id"],
                sid=evt["scene_id"],
            )


async def upsert_character_event(
    driver: AsyncDriver, character_id: str, event_id: str, role: str
) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (c:Character {id: $cid}), (e:TimelineEvent {id: $eid})
            MERGE (c)-[r:PARTICIPATES_IN {role: $role}]->(e)
            """,
            cid=character_id,
            eid=event_id,
            role=role,
        )


async def get_timeline_rows(
    driver: AsyncDriver,
    *,
    era: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    location: str | None = None,
) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (e:TimelineEvent)
            WHERE ($era IS NULL OR e.era = $era)
              AND ($date_from IS NULL OR e.date >= $date_from)
              AND ($date_to   IS NULL OR e.date <= $date_to)
            OPTIONAL MATCH (e)-[:AT_LOCATION]->(l:Location)
            WITH e, l
            WHERE $location IS NULL OR (l IS NOT NULL AND toLower(l.name) CONTAINS toLower($location))
            RETURN e.id AS id, e.date AS date, e.era AS era,
                   e.title AS title, e.description AS description,
                   l.id AS location_id, l.name AS location_name
            ORDER BY e.date
            """,
            era=era,
            date_from=date_from,
            date_to=date_to,
            location=location,
        )
        events = await result.data()

    rows: list[dict[str, Any]] = []
    for evt in events:
        async with driver.session() as session:
            chars_result = await session.run(
                """
                MATCH (c:Character)-[r:PARTICIPATES_IN]->(e:TimelineEvent {id: $eid})
                RETURN c.id AS character_id, c.name AS name
                """,
                eid=evt["id"],
            )
            chars = await chars_result.data()

        characters_detail = [{"id": c["character_id"], "name": c["name"]} for c in chars]
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


async def list_all_timeline_events(driver: AsyncDriver) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (e:TimelineEvent) RETURN e ORDER BY e.date"
        )
        return [dict(r["e"]) for r in await result.data()]


async def list_all_character_events(driver: AsyncDriver) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (c:Character)-[r:PARTICIPATES_IN]->(e:TimelineEvent)
            RETURN c.id AS character_id, e.id AS event_id, r.role AS role
            """
        )
        return [dict(r) for r in await result.data()]


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------


async def list_issues(
    driver: AsyncDriver,
    *,
    type: str | None = None,
    severity: str | None = None,
    resolved: bool | None = None,
) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (i:Issue)
            WHERE ($type IS NULL OR i.type = $type)
              AND ($severity IS NULL OR i.severity = $severity)
              AND ($resolved IS NULL OR i.resolved = $resolved)
            OPTIONAL MATCH (s:Scene)-[:HAS_ISSUE]->(i)
            RETURN i, s.id AS scene_id
            ORDER BY i.id DESC
            """,
            type=type,
            severity=severity,
            resolved=resolved,
        )
        rows = []
        for r in await result.data():
            d = dict(r["i"])
            d["scene_id"] = r["scene_id"]
            d["resolved"] = bool(d.get("resolved", False))
            rows.append(d)
        return rows


async def create_issue(driver: AsyncDriver, issue: dict[str, Any]) -> None:
    scene_id = issue.get("scene_id")
    async with driver.session() as session:
        await session.run(
            """
            MERGE (i:Issue {id: $id})
            SET i.type = $type, i.severity = $severity,
                i.entity_id = $entity_id, i.description = $description,
                i.suggestion = $suggestion, i.resolved = $resolved
            """,
            id=issue["id"],
            type=issue["type"],
            severity=issue["severity"],
            entity_id=issue.get("entity_id"),
            description=issue["description"],
            suggestion=issue.get("suggestion"),
            resolved=bool(issue.get("resolved", False)),
        )
        if scene_id:
            await session.run(
                """
                MATCH (s:Scene {id: $sid}), (i:Issue {id: $iid})
                MERGE (s)-[:HAS_ISSUE]->(i)
                """,
                sid=scene_id,
                iid=issue["id"],
            )


async def update_issue_resolved(
    driver: AsyncDriver, issue_id: str, resolved: bool
) -> bool:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (i:Issue {id: $id})
            SET i.resolved = $resolved
            RETURN i.id AS id
            """,
            id=issue_id,
            resolved=resolved,
        )
        record = await result.single()
        return record is not None


async def delete_issues_for_scenes(
    driver: AsyncDriver, scene_ids: list[str]
) -> None:
    if not scene_ids:
        return
    async with driver.session() as session:
        await session.run(
            """
            MATCH (s:Scene)-[:HAS_ISSUE]->(i:Issue)
            WHERE s.id IN $ids
            DETACH DELETE i
            """,
            ids=scene_ids,
        )
