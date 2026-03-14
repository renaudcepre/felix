from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite


async def list_characters(db: aiosqlite.Connection) -> str:
    cursor = await db.execute("SELECT id, name, era FROM characters ORDER BY era, name")
    rows = await cursor.fetchall()
    if not rows:
        return "No characters found in the bible."
    lines = ["Characters in the bible:"]
    for row in rows:
        lines.append(f"  - {row['name']} (id: {row['id']}, era: {row['era']})")
    return "\n".join(lines)


async def get_character(db: aiosqlite.Connection, character_id: str) -> str:
    cursor = await db.execute("SELECT * FROM characters WHERE id = ?", (character_id,))
    row = await cursor.fetchone()
    if row is None:
        return f"No character found with id '{character_id}'."

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
    rel_cursor = await db.execute(
        """
        SELECT cr.relation_type, cr.description, cr.era,
               CASE WHEN cr.character_id_a = ? THEN c2.name ELSE c1.name END AS other_name
        FROM character_relations cr
        JOIN characters c1 ON cr.character_id_a = c1.id
        JOIN characters c2 ON cr.character_id_b = c2.id
        WHERE cr.character_id_a = ? OR cr.character_id_b = ?
        """,
        (character_id, character_id, character_id),
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


async def list_locations(db: aiosqlite.Connection) -> str:
    cursor = await db.execute("SELECT id, name, era FROM locations ORDER BY era, name")
    rows = await cursor.fetchall()
    if not rows:
        return "No locations found in the bible."
    lines = ["Locations in the bible:"]
    for row in rows:
        era = f", era: {row['era']}" if row["era"] else ""
        lines.append(f"  - {row['name']} (id: {row['id']}{era})")
    return "\n".join(lines)


async def get_location(db: aiosqlite.Connection, location_id: str) -> str:
    cursor = await db.execute("SELECT * FROM locations WHERE id = ?", (location_id,))
    row = await cursor.fetchone()
    if row is None:
        return f"No location found with id '{location_id}'."

    lines = [
        f"Name: {row['name']}",
    ]
    if row["era"]:
        lines.append(f"Era: {row['era']}")
    if row["description"]:
        lines.append(f"Description: {row['description']}")
    if row["address"]:
        lines.append(f"Address: {row['address']}")

    return "\n".join(lines)


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
