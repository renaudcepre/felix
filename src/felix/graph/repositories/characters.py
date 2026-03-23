"""Neo4j repository — Character CRUD, fragments, aliases, relations."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from felix.graph.repositories._helpers import _nullify_empty

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncManagedTransaction

    from felix.graph.repositories._types import (
        CharacterFragmentExportRow,
        CharacterFragmentRow,
        CharacterProfileRow,
        CharacterRelationRow,
        CharacterSummaryRow,
        RelationRow,
    )


async def list_all_characters(driver: AsyncDriver) -> list[CharacterSummaryRow]:
    async def _read(tx: AsyncManagedTransaction) -> list[CharacterSummaryRow]:
        result = await tx.run(
            "MATCH (c:Character) RETURN c.id AS id, c.name AS name, c.era AS era"
            " ORDER BY c.era, c.name"
        )
        return cast("list[CharacterSummaryRow]", [dict(r) for r in await result.data()])

    async with driver.session() as session:
        return await session.execute_read(_read)


async def get_character_profile(
    driver: AsyncDriver, char_id: str
) -> CharacterProfileRow | None:
    async def _read(tx: AsyncManagedTransaction) -> CharacterProfileRow | None:
        result = await tx.run(
            "MATCH (c:Character {id: $id}) RETURN c", id=char_id
        )
        record = await result.single()
        if not record:
            return None
        return cast("CharacterProfileRow", dict(record["c"]))

    async with driver.session() as session:
        return await session.execute_read(_read)


async def get_character_relations(
    driver: AsyncDriver, char_id: str
) -> list[RelationRow]:
    async def _read(tx: AsyncManagedTransaction) -> list[RelationRow]:
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
        return cast("list[RelationRow]", [dict(r) for r in await result.data()])

    async with driver.session() as session:
        return await session.execute_read(_read)


async def list_all_characters_full(driver: AsyncDriver) -> list[CharacterProfileRow]:
    async def _read(tx: AsyncManagedTransaction) -> list[CharacterProfileRow]:
        result = await tx.run(
            "MATCH (c:Character) RETURN c ORDER BY c.era, c.name"
        )
        return cast("list[CharacterProfileRow]", [dict(r["c"]) for r in await result.data()])

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


async def list_all_character_relations(driver: AsyncDriver) -> list[CharacterRelationRow]:
    async def _read(tx: AsyncManagedTransaction) -> list[CharacterRelationRow]:
        result = await tx.run(
            """
            MATCH (a:Character)-[r:RELATED_TO]->(b:Character)
            RETURN a.id AS character_id_a, b.id AS character_id_b,
                   r.relation_type AS relation_type,
                   r.description AS description, r.era AS era
            """
        )
        return cast("list[CharacterRelationRow]", [dict(r) for r in await result.data()])

    async with driver.session() as session:
        return await session.execute_read(_read)


async def upsert_character_fragment(  # noqa: PLR0913
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
) -> list[CharacterFragmentRow]:
    async def _read(tx: AsyncManagedTransaction) -> list[CharacterFragmentRow]:
        result = await tx.run(
            """
            MATCH (c:Character {id: $cid})-[r:PRESENT_IN]->(s:Scene)
            RETURN s.id AS scene_id, r.role AS role, r.description AS description,
                   r.context AS context, s.title AS scene_title
            ORDER BY s.filename
            """,
            cid=character_id,
        )
        return cast("list[CharacterFragmentRow]", [dict(r) for r in await result.data()])

    async with driver.session() as session:
        return await session.execute_read(_read)


async def list_all_character_fragments(driver: AsyncDriver) -> list[CharacterFragmentExportRow]:
    async def _read(tx: AsyncManagedTransaction) -> list[CharacterFragmentExportRow]:
        result = await tx.run(
            """
            MATCH (c:Character)-[r:PRESENT_IN]->(s:Scene)
            RETURN c.id AS character_id, s.id AS scene_id,
                   r.role AS role, r.description AS description,
                   r.context AS context
            """
        )
        return cast("list[CharacterFragmentExportRow]", [dict(r) for r in await result.data()])

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
