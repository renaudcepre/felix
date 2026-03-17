from __future__ import annotations

from typing import Any

import kuzu


def delete_scenes(db: kuzu.Database, scene_ids: list[str]) -> None:
    """Remove scene nodes and their edges (idempotent re-import)."""
    if not scene_ids:
        return
    conn = kuzu.Connection(db)
    conn.execute(
        "MATCH ()-[r:PRESENT_IN]->(s:Scene) WHERE s.id IN $ids DELETE r",
        parameters={"ids": scene_ids},
    )
    conn.execute(
        "MATCH (s:Scene)-[r:AT_LOCATION]->() WHERE s.id IN $ids DELETE r",
        parameters={"ids": scene_ids},
    )
    conn.execute(
        "MATCH (s:Scene) WHERE s.id IN $ids DELETE s",
        parameters={"ids": scene_ids},
    )


def write_scene(db: kuzu.Database, scene_summary: dict[str, Any]) -> None:
    """Write Character, Scene, Location nodes and edges to the graph."""
    conn = kuzu.Connection(db)
    scene_id = scene_summary["scene_id"]
    loc = scene_summary["location"]

    conn.execute(
        "MERGE (l:Location {id: $id}) ON CREATE SET l.name = $name",
        parameters={"id": loc["id"], "name": loc["name"]},
    )
    conn.execute(
        "CREATE (:Scene {id: $id, title: $title, date: $date, era: $era})",
        parameters={
            "id": scene_id,
            "title": scene_summary.get("title"),
            "date": scene_summary.get("date"),
            "era": scene_summary.get("era"),
        },
    )
    conn.execute(
        "MATCH (s:Scene {id: $sid}), (l:Location {id: $lid}) CREATE (s)-[:AT_LOCATION]->(l)",
        parameters={"sid": scene_id, "lid": loc["id"]},
    )

    for char in scene_summary.get("characters", []):
        conn.execute(
            "MERGE (c:Character {id: $id}) ON CREATE SET c.name = $name",
            parameters={"id": char["id"], "name": char["name"]},
        )
        conn.execute(
            "MATCH (c:Character {id: $cid}), (s:Scene {id: $sid}) "
            "CREATE (c)-[:PRESENT_IN {role: $role}]->(s)",
            parameters={"cid": char["id"], "sid": scene_id, "role": char.get("role", "")},
        )
