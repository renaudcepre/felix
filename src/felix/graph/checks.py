"""Graph consistency checks — Neo4j async version."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncManagedTransaction

_BILOCALIZATION_QUERY = """
MATCH (c:Character)-[r1:PRESENT_IN]->(s1:Scene)-[:AT_LOCATION]->(l1:Location),
      (c)-[r2:PRESENT_IN]->(s2:Scene)-[:AT_LOCATION]->(l2:Location)
WHERE r1.role = 'participant'
  AND r2.role = 'participant'
  AND s1.date IS NOT NULL
  AND s1.date = s2.date
  AND l1.id <> l2.id
  AND (s1.id = $scene_id OR s2.id = $scene_id)
  AND s1.id < s2.id
RETURN c.id AS char_id, c.name AS char_name,
       s1.id AS s1_id, s1.title AS s1_title, l1.name AS l1_name,
       s2.id AS s2_id, s2.title AS s2_title, l2.name AS l2_name
"""


async def check_bilocalization(
    driver: AsyncDriver, scene_id: str
) -> list[dict[str, Any]]:
    """Detect characters present in two different locations on the same date."""
    async def _read(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(_BILOCALIZATION_QUERY, scene_id=scene_id)
        return await result.data()

    async with driver.session() as session:
        rows = await session.execute_read(_read)

    issues = []
    for row in rows:
        issues.append({
            "id": f"biloc-{row['char_id']}-{min(row['s1_id'], row['s2_id'])}-{max(row['s1_id'], row['s2_id'])}",
            "type": "bilocalization",
            "severity": "error",
            "scene_id": scene_id,
            "entity_id": row["char_id"],
            "description": (
                f"{row['char_name']} is present in both \"{row['s1_title']}\" ({row['l1_name']}) "
                f"and \"{row['s2_title']}\" ({row['l2_name']}) on the same date."
            ),
            "suggestion": (
                "Check the dates of both scenes or the character's role "
                "(a \"mentioned\" character can appear in multiple locations)."
            ),
        })
    return issues
