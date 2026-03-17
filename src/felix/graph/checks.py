from __future__ import annotations

import uuid
from typing import Any

import kuzu

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
RETURN c.id, c.name, s1.id, s1.title, l1.name, s2.id, s2.title, l2.name
"""


def check_bilocalization(db: kuzu.Database, scene_id: str) -> list[dict[str, Any]]:
    """Detect characters present in two different locations on the same date."""
    conn = kuzu.Connection(db)
    result = conn.execute(_BILOCALIZATION_QUERY, parameters={"scene_id": scene_id})
    issues = []
    while result.has_next():
        row = result.get_next()
        char_id, char_name, _s1_id, s1_title, l1_name, _s2_id, s2_title, l2_name = row
        issues.append({
            "id": str(uuid.uuid4()),
            "type": "bilocalization",
            "severity": "error",
            "scene_id": scene_id,
            "entity_id": char_id,
            "description": (
                f"{char_name} est présent(e) à la fois dans \"{s1_title}\" ({l1_name}) "
                f"et dans \"{s2_title}\" ({l2_name}) à la même date."
            ),
            "suggestion": (
                "Vérifiez les dates des deux scènes ou le rôle du personnage "
                "(un personnage \"mentionné\" peut apparaître dans plusieurs lieux)."
            ),
        })
    return issues
