"""Neo4j repository — async Cypher queries."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncManagedTransaction


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------


async def list_all_characters(driver: AsyncDriver) -> list[dict[str, Any]]:
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(
            "MATCH (c:Character) RETURN c.id AS id, c.name AS name, c.era AS era"
            " ORDER BY c.era, c.name"
        )
        return [dict(r) for r in await result.data()]

    async with driver.session() as session:
        return await session.execute_read(_read)


async def get_character_profile(
    driver: AsyncDriver, char_id: str
) -> dict[str, Any] | None:
    async def _read(tx: AsyncManagedTransaction) -> dict[str, Any] | None:
        result = await tx.run(
            "MATCH (c:Character {id: $id}) RETURN c", id=char_id
        )
        record = await result.single()
        if not record:
            return None
        return dict(record["c"])

    async with driver.session() as session:
        return await session.execute_read(_read)


async def get_character_relations(
    driver: AsyncDriver, char_id: str
) -> list[dict[str, Any]]:
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(
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

    async with driver.session() as session:
        return await session.execute_read(_read)


async def list_all_characters_full(driver: AsyncDriver) -> list[dict[str, Any]]:
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(
            "MATCH (c:Character) RETURN c ORDER BY c.era, c.name"
        )
        return [dict(r["c"]) for r in await result.data()]

    async with driver.session() as session:
        return await session.execute_read(_read)


async def upsert_character_minimal(
    driver: AsyncDriver, char: dict[str, Any]
) -> None:
    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MERGE (c:Character {id: $id})
            ON CREATE SET c.name = $name, c.era = $era
            """,
            id=char["id"],
            name=char["name"],
            era=char.get("era"),
        )

    async with driver.session() as session:
        await session.execute_write(_write)


async def update_character_profile(
    driver: AsyncDriver, char_id: str, profile: dict[str, str | None]
) -> None:
    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
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

    async with driver.session() as session:
        await session.execute_write(_write)


def _nullify_empty(v: str | None) -> str | None:
    return v if v and v.strip() else None


async def patch_character_profile_fields(
    driver: AsyncDriver, char_id: str, profile: dict[str, str | None]
) -> None:
    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MATCH (c:Character {id: $id})
            SET c.age        = CASE WHEN $age IS NOT NULL THEN $age ELSE c.age END,
                c.physical   = CASE WHEN $physical IS NOT NULL THEN $physical ELSE c.physical END,
                c.background = CASE
                                 WHEN $background IS NOT NULL AND c.background IS NOT NULL
                                   THEN c.background + '. ' + $background
                                 WHEN $background IS NOT NULL THEN $background
                                 ELSE c.background
                               END,
                c.arc        = CASE
                                 WHEN $arc IS NOT NULL AND c.arc IS NOT NULL
                                   THEN c.arc + '. ' + $arc
                                 WHEN $arc IS NOT NULL THEN $arc
                                 ELSE c.arc
                               END,
                c.traits     = CASE WHEN $traits IS NOT NULL THEN $traits ELSE c.traits END
            """,
            id=char_id,
            age=_nullify_empty(profile.get("age")),
            physical=_nullify_empty(profile.get("physical")),
            background=_nullify_empty(profile.get("background")),
            arc=_nullify_empty(profile.get("arc")),
            traits=_nullify_empty(profile.get("traits")),
        )

    async with driver.session() as session:
        await session.execute_write(_write)


async def overwrite_character_profile_fields(
    driver: AsyncDriver, char_id: str, fields: dict[str, str | None]
) -> bool:
    """SET direct des champs profil — édition manuelle, pas merge LLM."""
    allowed = {"age", "physical", "background", "arc", "traits"}
    params: dict[str, Any] = {"id": char_id}
    for f in allowed:
        params[f"{f}_set"] = f in fields
        params[f] = fields.get(f)

    async def _write(tx: AsyncManagedTransaction) -> bool:
        result = await tx.run(
            """
            MATCH (c:Character {id: $id})
            SET c.age        = CASE WHEN $age_set THEN $age ELSE c.age END,
                c.physical   = CASE WHEN $physical_set THEN $physical ELSE c.physical END,
                c.background = CASE WHEN $background_set THEN $background ELSE c.background END,
                c.arc        = CASE WHEN $arc_set THEN $arc ELSE c.arc END,
                c.traits     = CASE WHEN $traits_set THEN $traits ELSE c.traits END
            RETURN c.id AS id
            """,
            **params,
        )
        record = await result.single()
        return record is not None

    async with driver.session() as session:
        return await session.execute_write(_write)


async def delete_character_relation(
    driver: AsyncDriver,
    char_id_a: str,
    char_id_b: str,
    relation_type: str,
) -> bool:
    a, b = sorted([char_id_a, char_id_b])

    async def _write(tx: AsyncManagedTransaction) -> bool:
        result = await tx.run(
            """
            MATCH (a:Character {id: $a})-[r:RELATED_TO {relation_type: $type}]-(b:Character {id: $b})
            DELETE r
            RETURN count(r) AS deleted
            """,
            a=a,
            b=b,
            type=relation_type,
        )
        record = await result.single()
        return record is not None and record["deleted"] > 0

    async with driver.session() as session:
        return await session.execute_write(_write)


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


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


async def upsert_group_in_scene(
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


# ---------------------------------------------------------------------------
# Character relations
# ---------------------------------------------------------------------------


async def get_relation_types_for_pair(
    driver: AsyncDriver,
    char_id_a: str,
    char_id_b: str,
) -> list[str]:
    a, b = sorted([char_id_a, char_id_b])

    async def _read(tx: AsyncManagedTransaction) -> list[str]:
        result = await tx.run(
            """
            MATCH (a:Character {id: $a})-[r:RELATED_TO]-(b:Character {id: $b})
            RETURN r.relation_type AS relation_type
            """,
            a=a,
            b=b,
        )
        return [r["relation_type"] for r in await result.data()]

    async with driver.session() as session:
        return await session.execute_read(_read)


async def upsert_character_relation(  # noqa: PLR0913
    driver: AsyncDriver,
    char_id_a: str,
    char_id_b: str,
    relation_type: str,
    description: str | None = None,
    era: str | None = None,
) -> None:
    a, b = sorted([char_id_a, char_id_b])

    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
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

    async with driver.session() as session:
        await session.execute_write(_write)


async def list_all_character_relations(driver: AsyncDriver) -> list[dict[str, Any]]:
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(
            """
            MATCH (a:Character)-[r:RELATED_TO]->(b:Character)
            RETURN a.id AS character_id_a, b.id AS character_id_b,
                   r.relation_type AS relation_type,
                   r.description AS description, r.era AS era
            """
        )
        return [dict(r) for r in await result.data()]

    async with driver.session() as session:
        return await session.execute_read(_read)


# ---------------------------------------------------------------------------
# Character fragments (PRESENT_IN)
# ---------------------------------------------------------------------------


async def upsert_character_fragment(
    driver: AsyncDriver,
    character_id: str,
    scene_id: str,
    role: str | None,
    description: str | None,
    context: str | None = None,
) -> None:
    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MATCH (c:Character {id: $cid}), (s:Scene {id: $sid})
            MERGE (c)-[r:PRESENT_IN]->(s)
            SET r.role = $role, r.description = $description, r.context = $context
            """,
            cid=character_id,
            sid=scene_id,
            role=role or "",
            description=description,
            context=context,
        )

    async with driver.session() as session:
        await session.execute_write(_write)


async def get_character_fragments(
    driver: AsyncDriver, character_id: str
) -> list[dict[str, Any]]:
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(
            """
            MATCH (c:Character {id: $cid})-[r:PRESENT_IN]->(s:Scene)
            RETURN s.id AS scene_id, r.role AS role, r.description AS description,
                   r.context AS context, s.title AS scene_title
            ORDER BY s.filename
            """,
            cid=character_id,
        )
        return [dict(r) for r in await result.data()]

    async with driver.session() as session:
        return await session.execute_read(_read)


async def list_all_character_fragments(driver: AsyncDriver) -> list[dict[str, Any]]:
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(
            """
            MATCH (c:Character)-[r:PRESENT_IN]->(s:Scene)
            RETURN c.id AS character_id, s.id AS scene_id,
                   r.role AS role, r.description AS description,
                   r.context AS context
            """
        )
        return [dict(r) for r in await result.data()]

    async with driver.session() as session:
        return await session.execute_read(_read)


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------


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


async def add_character_alias(driver: AsyncDriver, char_id: str, alias: str) -> None:
    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MATCH (c:Character {id: $id})
            SET c.aliases = CASE
                WHEN $alias IN coalesce(c.aliases, []) THEN coalesce(c.aliases, [])
                ELSE coalesce(c.aliases, []) + [$alias]
            END
            """,
            id=char_id,
            alias=alias,
        )

    async with driver.session() as session:
        await session.execute_write(_write)


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


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------


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


async def list_scenes(driver: AsyncDriver) -> list[dict[str, Any]]:
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(
            """
            MATCH (s:Scene)
            RETURN s.id AS id, s.filename AS filename, s.title AS title,
                   s.era AS era, s.date AS date
            ORDER BY s.filename
            """
        )
        return [dict(r) for r in await result.data()]

    async with driver.session() as session:
        return await session.execute_read(_read)


async def get_scene_summaries_by_ids(
    driver: AsyncDriver,
    scene_ids: list[str],
) -> list[dict[str, Any]]:
    if not scene_ids:
        return []

    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
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
        return [dict(r) for r in await result.data()]

    async with driver.session() as session:
        return await session.execute_read(_read)


async def list_all_scenes_full(driver: AsyncDriver) -> list[dict[str, Any]]:
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(
            "MATCH (s:Scene) RETURN s ORDER BY s.filename"
        )
        return [dict(r["s"]) for r in await result.data()]

    async with driver.session() as session:
        return await session.execute_read(_read)


# ---------------------------------------------------------------------------
# Timeline events
# ---------------------------------------------------------------------------


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
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(
            """
            MATCH (i:Issue)
            WHERE ($type IS NULL OR i.type = $type)
              AND ($severity IS NULL OR i.severity = $severity)
              AND ($resolved IS NULL OR i.resolved = $resolved)
            OPTIONAL MATCH (s:Scene)-[:HAS_ISSUE]->(i)
            RETURN i, s.id AS scene_id
            ORDER BY i.created_at DESC
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

    async with driver.session() as session:
        return await session.execute_read(_read)


async def get_issue_by_id(
    driver: AsyncDriver, issue_id: str
) -> dict[str, Any] | None:
    async def _read(tx: AsyncManagedTransaction) -> dict[str, Any] | None:
        result = await tx.run(
            """
            MATCH (i:Issue {id: $id})
            OPTIONAL MATCH (s:Scene)-[:HAS_ISSUE]->(i)
            RETURN i, s.id AS scene_id
            """,
            id=issue_id,
        )
        record = await result.single()
        if not record:
            return None
        d = dict(record["i"])
        d["scene_id"] = record["scene_id"]
        d["resolved"] = bool(d.get("resolved", False))
        return d

    async with driver.session() as session:
        return await session.execute_read(_read)


async def create_issue(driver: AsyncDriver, issue: dict[str, Any]) -> None:
    scene_id = issue.get("scene_id")

    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MERGE (i:Issue {id: $id})
            ON CREATE SET i.created_at = datetime()
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
            await tx.run(
                """
                MATCH (s:Scene {id: $sid}), (i:Issue {id: $iid})
                MERGE (s)-[:HAS_ISSUE]->(i)
                """,
                sid=scene_id,
                iid=issue["id"],
            )

    async with driver.session() as session:
        await session.execute_write(_write)


async def update_issue_resolved(
    driver: AsyncDriver, issue_id: str, resolved: bool
) -> bool:
    async def _write(tx: AsyncManagedTransaction) -> bool:
        result = await tx.run(
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

    async with driver.session() as session:
        return await session.execute_write(_write)


async def delete_issues_for_scenes(
    driver: AsyncDriver, scene_ids: list[str]
) -> None:
    if not scene_ids:
        return

    async def _write(tx: AsyncManagedTransaction) -> None:
        await tx.run(
            """
            MATCH (s:Scene)-[:HAS_ISSUE]->(i:Issue)
            WHERE s.id IN $ids
            DETACH DELETE i
            """,
            ids=scene_ids,
        )

    async with driver.session() as session:
        await session.execute_write(_write)


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


# ---------------------------------------------------------------------------
# Narrative Beats
# ---------------------------------------------------------------------------


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
