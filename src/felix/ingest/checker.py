from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.graph.repositories.scenes import get_scene_summaries_by_ids
from felix.ingest.models import ConsistencyReport
from felix.llm import build_model

if TYPE_CHECKING:
    import chromadb
    from neo4j import AsyncDriver
    from pydantic_ai.models import Model

logger = logging.getLogger("felix.ingest.checker")

CHECKER_TIMELINE_PROMPT = """\
You are a specialized assistant for checking temporal consistency in screenplays.

You are given a chronologically sorted list of scenes (scene_id, title, summary, date, era).

IMPORTANT CONTEXT:
- Scenes can span multiple eras (e.g. 1940s, 1970s, 2050s, 2140s).
- Characters sharing the same last name may be DIFFERENT people.
- An entity (object, AI, organization) can EVOLVE over time — this is NOT an inconsistency.

Detect ONLY real TEMPORAL inconsistencies:
- timeline_inconsistency: impossible dates, anachronisms, events in the wrong order,
  contradictory dates between scenes

DO NOT REPORT:
- Characters from the same family with similar names (they are different people)
- Normal evolution of an entity over time
- Any non-temporal inconsistency (character contradictions, missing info...)

For each problem, provide:
- type: "timeline_inconsistency"
- severity: "error" (certain) or "warning" (suspected)
- scene_id: the ID of the affected scene
- entity_id: the ID of the affected entity if applicable, otherwise null
- description: clear description
- suggestion: correction suggestion

If everything is consistent, return an empty issues list.
"""

CHECKER_NARRATIVE_PROMPT = """\
You are a specialized assistant for checking narrative consistency in screenplays.

You are given:
- "current_scene": the scene to verify (scene_id, title, summary, characters, location)
- "related_scenes": semantically related scenes (scene_id, title, summary)

IMPORTANT CONTEXT:
- Characters sharing the same last name may be DIFFERENT people.
- A character with role "mentioned" is NOT physically present — they are merely evoked.
- A dead character can be mentioned in later scenes — this is NOT an inconsistency.

Detect ONLY real NARRATIVE inconsistencies in the current scene:
- character_contradiction: a character does something incompatible with what we know
  about them from previous scenes (same character, not a namesake or descendant)
- missing_info: a character reacts to information they cannot yet know
  based on previous scenes

DO NOT REPORT:
- Temporal inconsistencies (dates, anachronisms) — that is not your domain
- Characters from the same family with similar names
- Normal evolution of entities over time

For each problem, provide:
- type: "character_contradiction" or "missing_info"
- severity: "error" (certain) or "warning" (suspected)
- scene_id: the ID of the affected scene (the scene_id of the current_scene)
- entity_id: the ID of the affected entity if applicable, otherwise null
- description: clear description
- suggestion: correction suggestion

If everything is consistent, return an empty issues list.
"""


def _create_checker_agent(
    prompt: str,
    model_name: str | None = None,
    base_url: str | None = None,
) -> Agent[None, ConsistencyReport]:
    model: Model = build_model(model_name, base_url)
    return Agent(
        model,
        instructions=prompt,
        output_type=ConsistencyReport,
        model_settings=ModelSettings(temperature=0.1),
        retries=2,
    )


def create_checker_agents(
    model_name: str | None = None,
    base_url: str | None = None,
) -> tuple[Agent[None, ConsistencyReport], Agent[None, ConsistencyReport]]:
    """Create timeline and narrative checker agents (one-time, reusable)."""
    return (
        _create_checker_agent(CHECKER_TIMELINE_PROMPT, model_name, base_url),
        _create_checker_agent(CHECKER_NARRATIVE_PROMPT, model_name, base_url),
    )


async def check_scene_consistency(
    driver: AsyncDriver,
    collection: chromadb.Collection,
    scene_summary: dict[str, Any],
    timeline_agent: Agent[None, ConsistencyReport],
    narrative_agent: Agent[None, ConsistencyReport],
) -> ConsistencyReport:
    current_scene_id = scene_summary["scene_id"]

    # 1. Retrieval ChromaDB
    char_names = [c["name"] for c in scene_summary.get("characters", [])]
    location_name = scene_summary.get("location", {}).get("name", "")
    query_text = f"{' '.join(char_names)} {location_name}".strip()

    relevant_summaries: list[dict[str, Any]] = []
    if query_text:
        total = collection.count()
        n = min(11, total)
        if n > 0:
            results = collection.query(query_texts=[query_text], n_results=n)
            metadatas = results.get("metadatas") or [[]]
            relevant_ids: list[str] = [
                str(m["scene_id"])
                for m in metadatas[0]
                if m.get("scene_id") and m["scene_id"] != current_scene_id
            ][:10]
            if relevant_ids:
                relevant_summaries = await get_scene_summaries_by_ids(driver, relevant_ids)

    # 2. Pass 1 — Timeline
    timeline_scenes = [
        {
            "scene_id": s["id"],
            "era": s["era"],
            "date": s["date"],
            "title": s["title"],
            "summary": s["summary"],
        }
        for s in relevant_summaries
    ] + [
        {
            "scene_id": current_scene_id,
            "era": scene_summary.get("era"),
            "date": scene_summary.get("date"),
            "title": scene_summary.get("title"),
            "summary": scene_summary.get("summary"),
        }
    ]
    timeline_scenes.sort(key=lambda s: (s["date"] is None, s["date"] or ""))

    timeline_result = await timeline_agent.run(
        json.dumps(timeline_scenes, ensure_ascii=False, indent=2)
    )
    timeline_report = timeline_result.output

    # 3. Pass 2 — Narrative
    narrative_input = {
        "current_scene": {
            "scene_id": current_scene_id,
            "title": scene_summary.get("title"),
            "summary": scene_summary.get("summary"),
            "characters": scene_summary.get("characters", []),
            "location": scene_summary.get("location", {}),
        },
        "related_scenes": [
            {
                "scene_id": s["id"],
                "title": s["title"],
                "summary": s["summary"],
            }
            for s in relevant_summaries
        ],
    }

    narrative_result = await narrative_agent.run(
        json.dumps(narrative_input, ensure_ascii=False, indent=2)
    )
    narrative_report = narrative_result.output

    return ConsistencyReport(issues=timeline_report.issues + narrative_report.issues)
