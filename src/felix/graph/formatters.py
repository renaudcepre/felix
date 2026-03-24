"""Text formatters for the Felix agent — Neo4j version."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncManagedTransaction

from felix.graph.repositories.timeline import get_timeline_rows


def _format_character_profile(  # noqa: PLR0912
    row: dict, relations: list[dict], fragments: list[dict], groups: list[dict] | None = None,
) -> str:
    lines = [
        f"Name: {row['name']}",
        f"Era: {row['era']}",
    ]
    aliases = row.get("aliases")
    if aliases:
        lines.append(f"Aliases: {', '.join(aliases)}")
    if row.get("age"):
        lines.append(f"Age: {row['age']}")
    if row.get("physical"):
        lines.append(f"Physical: {row['physical']}")
    if row.get("background"):
        lines.append(f"Background: {row['background']}")
    if row.get("arc"):
        lines.append(f"Arc: {row['arc']}")
    if row.get("traits"):
        lines.append(f"Traits: {row['traits']}")
    if row.get("status"):
        lines.append(f"Status: {row['status']}")

    if relations:
        lines.append("Relations:")
        for rel in relations:
            desc = f" — {rel['description']}" if rel.get("description") else ""
            era = f" ({rel['era']})" if rel.get("era") else ""
            lines.append(
                f"  - {rel['relation_type']} with {rel['other_name']}{era}{desc}"
            )

    if groups:
        lines.append("Groups:")
        for g in groups:
            lines.append(f"  - {g['name']}")

    if fragments:
        lines.append("Scene observations:")
        for frag in fragments:
            title = frag.get("scene_title") or frag["scene_id"]
            role_str = f" [{frag['role']}]" if frag.get("role") else ""
            desc = f" — {frag['description']}" if frag.get("description") else ""
            lines.append(f"  - {title}{role_str}{desc}")

    return "\n".join(lines)


async def find_character(driver: AsyncDriver, name: str) -> str:
    async def _read(tx: AsyncManagedTransaction) -> list[dict]:
        result = await tx.run(
            """
            MATCH (c:Character)
            WHERE toLower(c.name) CONTAINS toLower($name)
               OR any(a IN c.aliases WHERE toLower(a) CONTAINS toLower($name))
            WITH c ORDER BY c.era, c.name
            CALL (c) {
                MATCH (c)-[rel:RELATED_TO]-(other:Character)
                RETURN collect({
                    relation_type: rel.relation_type,
                    other_name: other.name,
                    era: rel.era,
                    description: rel.description
                }) AS relations
            }
            CALL (c) {
                MATCH (c)-[r:PRESENT_IN]->(s:Scene)
                RETURN collect({
                    scene_id: s.id,
                    scene_title: s.title,
                    role: r.role,
                    description: r.description
                }) AS fragments
            }
            CALL (c) {
                OPTIONAL MATCH (c)-[:MEMBER_OF]->(g:Group)
                RETURN collect({id: g.id, name: g.name}) AS groups
            }
            RETURN c, relations, fragments, groups
            """,
            name=name,
        )
        return await result.data()

    async with driver.session() as session:
        rows = await session.execute_read(_read)

    if not rows:
        async def _fallback(tx: AsyncManagedTransaction) -> list[dict]:
            result = await tx.run(
                "MATCH (c:Character) RETURN c.name AS name ORDER BY c.era, c.name"
            )
            return await result.data()

        async with driver.session() as session:
            names = ", ".join(r["name"] for r in await session.execute_read(_fallback))
        return f"No character matching '{name}'. Available: {names}"

    profiles = []
    for row in rows:
        grps = [g for g in row.get("groups", []) if g.get("id")]
        profiles.append(_format_character_profile(dict(row["c"]), row["relations"], row["fragments"], grps))

    return "\n---\n".join(profiles)


async def find_location(driver: AsyncDriver, name: str) -> str:
    async def _read(tx: AsyncManagedTransaction) -> list[dict]:
        result = await tx.run(
            """
            MATCH (l:Location)
            WHERE toLower(l.name) CONTAINS toLower($name)
            RETURN l
            ORDER BY l.era, l.name
            """,
            name=name,
        )
        return [dict(r["l"]) for r in await result.data()]

    async with driver.session() as session:
        rows = await session.execute_read(_read)

    if not rows:
        async def _fallback(tx: AsyncManagedTransaction) -> list[dict]:
            result = await tx.run(
                "MATCH (l:Location) RETURN l.name AS name ORDER BY l.era, l.name"
            )
            return await result.data()

        async with driver.session() as session:
            names = ", ".join(r["name"] for r in await session.execute_read(_fallback))
        return f"No location matching '{name}'. Available: {names}"

    profiles = []
    for row in rows:
        lines = [f"Name: {row['name']}"]
        if row.get("era"):
            lines.append(f"Era: {row['era']}")
        if row.get("description"):
            lines.append(f"Description: {row['description']}")
        if row.get("address"):
            lines.append(f"Address: {row['address']}")
        profiles.append("\n".join(lines))

    return "\n---\n".join(profiles)


async def get_timeline(
    driver: AsyncDriver,
    *,
    era: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    location: str | None = None,
) -> str:
    rows = await get_timeline_rows(
        driver, era=era, date_from=date_from, date_to=date_to, location=location
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
        loc_str = f" @ {row['location']}" if row["location"] else ""
        lines.append(f"  [{row['date']}] {row['title']}{loc_str}")
        if row["description"]:
            lines.append(f"    {row['description']}")
        if row["characters_detail"]:
            char_strs = [c["name"] for c in row["characters_detail"]]
            lines.append(f"    Characters: {', '.join(char_strs)}")

    return "\n".join(lines)
