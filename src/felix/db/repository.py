from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiosqlite


async def list_all_characters(db: aiosqlite.Connection) -> list[aiosqlite.Row]:
    cursor = await db.execute(
        "SELECT id, name, era FROM characters ORDER BY era, name"
    )
    return list(await cursor.fetchall())


async def get_character_profile(
    db: aiosqlite.Connection, char_id: str
) -> aiosqlite.Row | None:
    cursor = await db.execute(
        "SELECT * FROM characters WHERE id = ?", (char_id,)
    )
    return await cursor.fetchone()


async def get_character_relations(
    db: aiosqlite.Connection, char_id: str
) -> list[aiosqlite.Row]:
    cursor = await db.execute(
        """
        SELECT cr.relation_type, cr.description, cr.era,
               CASE WHEN cr.character_id_a = ? THEN c2.name ELSE c1.name END AS other_name
        FROM character_relations cr
        JOIN characters c1 ON cr.character_id_a = c1.id
        JOIN characters c2 ON cr.character_id_b = c2.id
        WHERE cr.character_id_a = ? OR cr.character_id_b = ?
        """,
        (char_id, char_id, char_id),
    )
    return list(await cursor.fetchall())


async def get_timeline_rows(
    db: aiosqlite.Connection,
    *,
    era: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    location: str | None = None,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[str] = []

    if era:
        conditions.append("te.era = ?")
        params.append(era)
    if date_from:
        conditions.append("te.date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("te.date <= ?")
        params.append(date_to)
    if location:
        conditions.append("LOWER(l.name) LIKE '%' || LOWER(?) || '%'")
        params.append(location)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    join_type = "INNER" if location else "LEFT"

    query = f"""
        SELECT te.id, te.date, te.era, te.title, te.description,
               te.location_id, l.name AS location_name
        FROM timeline_events te
        {join_type} JOIN locations l ON te.location_id = l.id
        {where}
        ORDER BY te.date
    """  # noqa: S608
    cursor = await db.execute(query, params)
    events = await cursor.fetchall()

    rows: list[dict[str, Any]] = []
    for evt in events:
        char_cursor = await db.execute(
            """
            SELECT ce.character_id, c.name
            FROM character_events ce
            JOIN characters c ON ce.character_id = c.id
            WHERE ce.event_id = ?
            """,
            (evt["id"],),
        )
        chars = await char_cursor.fetchall()
        characters_detail = [
            {"id": c["character_id"], "name": c["name"]}
            for c in chars
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


async def list_issues(
    db: aiosqlite.Connection,
    *,
    type: str | None = None,
    severity: str | None = None,
    resolved: bool | None = None,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if type:
        conditions.append("type = ?")
        params.append(type)
    if severity:
        conditions.append("severity = ?")
        params.append(severity)
    if resolved is not None:
        conditions.append("resolved = ?")
        params.append(int(resolved))
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM issues {where} ORDER BY created_at DESC"  # noqa: S608
    cursor = await db.execute(query, params)
    return [dict(row) for row in await cursor.fetchall()]


async def create_issue(db: aiosqlite.Connection, issue: dict[str, Any]) -> None:
    await db.execute(
        """
        INSERT INTO issues (id, type, severity, scene_id, entity_id, description, suggestion, resolved)
        VALUES (:id, :type, :severity, :scene_id, :entity_id, :description, :suggestion, :resolved)
        """,
        {**issue, "resolved": issue.get("resolved", 0)},
    )
    await db.commit()


async def update_issue_resolved(
    db: aiosqlite.Connection, issue_id: str, resolved: bool
) -> bool:
    cursor = await db.execute(
        "UPDATE issues SET resolved = ? WHERE id = ?",
        (int(resolved), issue_id),
    )
    await db.commit()
    return cursor.rowcount > 0


async def delete_issues_for_scenes(
    db: aiosqlite.Connection, scene_ids: list[str]
) -> None:
    if not scene_ids:
        return
    placeholders = ",".join("?" for _ in scene_ids)
    await db.execute(
        f"DELETE FROM issues WHERE scene_id IN ({placeholders})",  # noqa: S608
        scene_ids,
    )
    await db.commit()


async def list_scenes(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    cursor = await db.execute(
        "SELECT id, filename, title, era, date FROM scenes ORDER BY filename"
    )
    return [dict(row) for row in await cursor.fetchall()]


async def upsert_scene(db: aiosqlite.Connection, scene: dict[str, Any]) -> None:
    await db.execute(
        """
        INSERT OR REPLACE INTO scenes (id, filename, title, summary, era, date, location_id, raw_text)
        VALUES (:id, :filename, :title, :summary, :era, :date, :location_id, :raw_text)
        """,
        scene,
    )
    await db.commit()


async def upsert_character_minimal(
    db: aiosqlite.Connection, char: dict[str, Any]
) -> None:
    await db.execute(
        """
        INSERT OR IGNORE INTO characters (id, name, era)
        VALUES (:id, :name, :era)
        """,
        char,
    )
    await db.commit()


async def upsert_location_minimal(
    db: aiosqlite.Connection, loc: dict[str, Any]
) -> None:
    await db.execute(
        """
        INSERT OR IGNORE INTO locations (id, name, description)
        VALUES (:id, :name, :description)
        """,
        loc,
    )
    await db.commit()


async def upsert_timeline_event(
    db: aiosqlite.Connection, evt: dict[str, Any]
) -> None:
    await db.execute(
        """
        INSERT OR REPLACE INTO timeline_events (id, date, era, title, description, location_id, scene_id)
        VALUES (:id, :date, :era, :title, :description, :location_id, :scene_id)
        """,
        evt,
    )
    await db.commit()


async def upsert_character_event(
    db: aiosqlite.Connection, character_id: str, event_id: str, role: str
) -> None:
    await db.execute(
        """
        INSERT OR REPLACE INTO character_events (character_id, event_id, role)
        VALUES (?, ?, ?)
        """,
        (character_id, event_id, role),
    )
    await db.commit()


async def upsert_character_fragment(
    db: aiosqlite.Connection,
    character_id: str,
    scene_id: str,
    role: str | None,
    description: str | None,
) -> None:
    await db.execute(
        """
        INSERT OR REPLACE INTO character_fragments (character_id, scene_id, role, description)
        VALUES (?, ?, ?, ?)
        """,
        (character_id, scene_id, role, description),
    )
    await db.commit()


async def get_character_fragments(
    db: aiosqlite.Connection, character_id: str
) -> list[dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT cf.scene_id, cf.role, cf.description, s.title AS scene_title
        FROM character_fragments cf
        LEFT JOIN scenes s ON cf.scene_id = s.id
        WHERE cf.character_id = ?
        ORDER BY s.filename
        """,
        (character_id,),
    )
    return [dict(row) for row in await cursor.fetchall()]


async def update_character_profile(
    db: aiosqlite.Connection, char_id: str, profile: dict[str, str | None]
) -> None:
    await db.execute(
        """
        UPDATE characters SET
            age        = COALESCE(age, :age),
            physical   = COALESCE(physical, :physical),
            background = COALESCE(background, :background),
            arc        = COALESCE(arc, :arc),
            traits     = COALESCE(traits, :traits)
        WHERE id = :id
        """,
        {
            "id": char_id,
            "age": profile.get("age"),
            "physical": profile.get("physical"),
            "background": profile.get("background"),
            "arc": profile.get("arc"),
            "traits": profile.get("traits"),
        },
    )
    await db.commit()


async def get_relation_types_for_pair(
    db: aiosqlite.Connection,
    char_id_a: str,
    char_id_b: str,
) -> list[str]:
    a, b = sorted([char_id_a, char_id_b])
    cursor = await db.execute(
        "SELECT relation_type FROM character_relations WHERE character_id_a = ? AND character_id_b = ?",
        (a, b),
    )
    return [row[0] for row in await cursor.fetchall()]


async def upsert_character_relation(  # noqa: PLR0913
    db: aiosqlite.Connection,
    char_id_a: str,
    char_id_b: str,
    relation_type: str,
    description: str | None = None,
    era: str | None = None,
) -> None:
    await db.execute(
        """
        INSERT OR REPLACE INTO character_relations
            (character_id_a, character_id_b, relation_type, description, era)
        VALUES (?, ?, ?, ?, ?)
        """,
        (char_id_a, char_id_b, relation_type, description, era),
    )
    await db.commit()


async def list_all_characters_full(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    cursor = await db.execute("SELECT * FROM characters ORDER BY era, name")
    return [dict(row) for row in await cursor.fetchall()]


async def list_all_locations(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    cursor = await db.execute("SELECT * FROM locations ORDER BY era, name")
    return [dict(row) for row in await cursor.fetchall()]


async def get_location_detail(
    db: aiosqlite.Connection, loc_id: str
) -> dict[str, Any] | None:
    cursor = await db.execute(
        "SELECT * FROM locations WHERE id = ?", (loc_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None

    scenes_cursor = await db.execute(
        "SELECT id, filename, title, era, date FROM scenes WHERE location_id = ? ORDER BY filename",
        (loc_id,),
    )
    scenes = [dict(s) for s in await scenes_cursor.fetchall()]
    return {**dict(row), "scenes": scenes}


async def list_all_scenes_full(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    cursor = await db.execute("SELECT * FROM scenes ORDER BY filename")
    return [dict(row) for row in await cursor.fetchall()]


async def list_all_timeline_events(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    cursor = await db.execute("SELECT * FROM timeline_events ORDER BY date")
    return [dict(row) for row in await cursor.fetchall()]


async def list_all_character_events(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    cursor = await db.execute("SELECT * FROM character_events")
    return [dict(row) for row in await cursor.fetchall()]


async def list_all_character_relations(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    cursor = await db.execute("SELECT * FROM character_relations")
    return [dict(row) for row in await cursor.fetchall()]


async def list_all_character_fragments(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    cursor = await db.execute("SELECT * FROM character_fragments")
    return [dict(row) for row in await cursor.fetchall()]
