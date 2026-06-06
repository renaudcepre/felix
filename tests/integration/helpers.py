from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver


async def insert_character(driver: AsyncDriver, char_id: str, **fields: object) -> None:
    props = {"id": char_id, "name": char_id, "era": "2030s", **fields}
    set_clauses = ", ".join(f"c.{k} = ${k}" for k in props if k != "id")
    async with driver.session() as session:
        await session.run(
            f"MERGE (c:Character {{id: $id}}) SET {set_clauses}",
            **props,
        )


async def get_char(driver: AsyncDriver, char_id: str) -> dict:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Character {id: $id}) RETURN c", id=char_id
        )
        record = await result.single()
        return dict(record["c"]) if record else {}
