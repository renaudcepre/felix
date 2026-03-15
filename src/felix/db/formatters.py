from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

from felix.db import repository


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

    char_id = row["id"]
    relations = await repository.get_character_relations(db, char_id)
    if relations:
        lines.append("Relations:")
        for rel in relations:
            desc = f" — {rel['description']}" if rel["description"] else ""
            era = f" ({rel['era']})" if rel["era"] else ""
            lines.append(
                f"  - {rel['relation_type']} with {rel['other_name']}{era}{desc}"
            )

    fragments = await repository.get_character_fragments(db, char_id)
    if fragments:
        lines.append("Observations par scene:")
        for frag in fragments:
            title = frag["scene_title"] or frag["scene_id"]
            role_str = f" [{frag['role']}]" if frag["role"] else ""
            desc = f" — {frag['description']}" if frag["description"] else ""
            lines.append(f"  - {title}{role_str}{desc}")

    return "\n".join(lines)


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


async def get_timeline(
    db: aiosqlite.Connection,
    *,
    era: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    location: str | None = None,
) -> str:
    rows = await repository.get_timeline_rows(
        db, era=era, date_from=date_from, date_to=date_to, location=location
    )

    if not rows:
        filters = []
        if era:
            filters.append(f"era={era}")
        if date_from:
            filters.append(f"from={date_from}")
        if date_to:
            filters.append(f"to={date_to}")
        if location:
            filters.append(f"location={location}")
        filter_str = ", ".join(filters) if filters else "none"
        return f"No timeline events found (filters: {filter_str})."

    lines = [f"Timeline events ({len(rows)} found):"]
    for row in rows:
        location = f" @ {row['location']}" if row["location"] else ""
        lines.append(f"  [{row['date']}] {row['title']}{location}")
        if row["description"]:
            lines.append(f"    {row['description']}")

        char_cursor = await db.execute(
            """
            SELECT c.name, ce.role
            FROM character_events ce
            JOIN characters c ON ce.character_id = c.id
            WHERE ce.event_id = ?
            """,
            (row["id"],),
        )
        chars = await char_cursor.fetchall()
        if chars:
            char_strs = [
                f"{c['name']} ({c['role']})" if c["role"] else c["name"] for c in chars
            ]
            lines.append(f"    Characters: {', '.join(char_strs)}")

    return "\n".join(lines)
