from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiosqlite


async def _format_character_profile(db: aiosqlite.Connection, row: aiosqlite.Row) -> str:
    lines = [
        f"Name: {row['name']}",
        f"Era: {row['era']}",
    ]
    if row["aliases"]:
        aliases = json.loads(row["aliases"])
        lines.append(f"Aliases: {', '.join(aliases)}")
    if row["age"]:
        lines.append(f"Age: {row['age']}")
    if row["physical"]:
        lines.append(f"Physical: {row['physical']}")
    if row["background"]:
        lines.append(f"Background: {row['background']}")
    if row["arc"]:
        lines.append(f"Arc: {row['arc']}")
    if row["traits"]:
        lines.append(f"Traits: {row['traits']}")
    if row["status"]:
        lines.append(f"Status: {row['status']}")

    # Fetch relations
    char_id = row["id"]
    rel_cursor = await db.execute(
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
    relations = await rel_cursor.fetchall()
    if relations:
        lines.append("Relations:")
        for rel in relations:
            desc = f" — {rel['description']}" if rel["description"] else ""
            era = f" ({rel['era']})" if rel["era"] else ""
            lines.append(
                f"  - {rel['relation_type']} with {rel['other_name']}{era}{desc}"
            )

    return "\n".join(lines)


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

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT te.id, te.date, te.era, te.title, te.description,
               l.name AS location_name
        FROM timeline_events te
        LEFT JOIN locations l ON te.location_id = l.id
        {where}
        ORDER BY te.date
    """  # noqa: S608
    cursor = await db.execute(query, params)
    events = await cursor.fetchall()

    rows: list[dict[str, Any]] = []
    for evt in events:
        char_cursor = await db.execute(
            """
            SELECT c.name, ce.role
            FROM character_events ce
            JOIN characters c ON ce.character_id = c.id
            WHERE ce.event_id = ?
            """,
            (evt["id"],),
        )
        chars = await char_cursor.fetchall()
        char_strs = [
            f"{c['name']} ({c['role']})" if c["role"] else c["name"]
            for c in chars
        ]
        rows.append({
            "id": evt["id"],
            "date": evt["date"],
            "era": evt["era"],
            "title": evt["title"],
            "description": evt["description"] or "",
            "location": evt["location_name"] or "",
            "characters": ", ".join(char_strs),
        })

    return rows


async def find_character(db: aiosqlite.Connection, name: str) -> str:
    cursor = await db.execute(
        """
        SELECT * FROM characters
        WHERE LOWER(name) LIKE '%' || LOWER(?) || '%'
           OR LOWER(aliases) LIKE '%' || LOWER(?) || '%'
        ORDER BY era, name
        """,
        (name, name),
    )
    rows = await cursor.fetchall()

    if not rows:
        all_cursor = await db.execute(
            "SELECT name FROM characters ORDER BY era, name"
        )
        all_rows = await all_cursor.fetchall()
        names = ", ".join(r["name"] for r in all_rows)
        return f"Aucun personnage correspondant a '{name}'. Disponibles : {names}"

    profiles = []
    for row in rows:
        profiles.append(await _format_character_profile(db, row))

    return "\n---\n".join(profiles)


async def find_location(db: aiosqlite.Connection, name: str) -> str:
    cursor = await db.execute(
        """
        SELECT * FROM locations
        WHERE LOWER(name) LIKE '%' || LOWER(?) || '%'
        ORDER BY era, name
        """,
        (name,),
    )
    rows = await cursor.fetchall()

    if not rows:
        all_cursor = await db.execute(
            "SELECT name FROM locations ORDER BY era, name"
        )
        all_rows = await all_cursor.fetchall()
        names = ", ".join(r["name"] for r in all_rows)
        return f"Aucun lieu correspondant a '{name}'. Disponibles : {names}"

    profiles = []
    for row in rows:
        lines = [f"Name: {row['name']}"]
        if row["era"]:
            lines.append(f"Era: {row['era']}")
        if row["description"]:
            lines.append(f"Description: {row['description']}")
        if row["address"]:
            lines.append(f"Address: {row['address']}")
        profiles.append("\n".join(lines))

    return "\n---\n".join(profiles)


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


async def get_timeline(
    db: aiosqlite.Connection,
    *,
    era: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
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

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT te.id, te.date, te.era, te.title, te.description,
               l.name AS location_name
        FROM timeline_events te
        LEFT JOIN locations l ON te.location_id = l.id
        {where}
        ORDER BY te.date
    """  # noqa: S608
    cursor = await db.execute(query, params)
    events = await cursor.fetchall()

    if not events:
        filters = []
        if era:
            filters.append(f"era={era}")
        if date_from:
            filters.append(f"from={date_from}")
        if date_to:
            filters.append(f"to={date_to}")
        filter_str = ", ".join(filters) if filters else "none"
        return f"No timeline events found (filters: {filter_str})."

    lines = [f"Timeline events ({len(events)} found):"]
    for evt in events:
        location = f" @ {evt['location_name']}" if evt["location_name"] else ""
        lines.append(f"  [{evt['date']}] {evt['title']}{location}")
        if evt["description"]:
            lines.append(f"    {evt['description']}")

        # Fetch characters involved
        char_cursor = await db.execute(
            """
            SELECT c.name, ce.role
            FROM character_events ce
            JOIN characters c ON ce.character_id = c.id
            WHERE ce.event_id = ?
            """,
            (evt["id"],),
        )
        chars = await char_cursor.fetchall()
        if chars:
            char_strs = [
                f"{c['name']} ({c['role']})" if c["role"] else c["name"] for c in chars
            ]
            lines.append(f"    Characters: {', '.join(char_strs)}")

    return "\n".join(lines)
