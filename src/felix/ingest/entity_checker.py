"""Entity-level consistency checker — validates profile edits against scene evidence."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.graph.repositories.characters import (
    get_character_fragments,
    get_character_profile,
    get_character_relations,
)
from felix.graph.repositories.scenes import get_scene_summaries_by_ids
from felix.ingest.models import ConsistencyReport
from felix.ingest.utils import normalize
from felix.llm import build_model

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = logging.getLogger("felix.ingest.entity_checker")



def _find_evidence(
    proposed_fields: dict[str, str | None],
    raw_texts: list[tuple[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """For each proposed field, find which raw_text fragments contain matching phrases.

    Returns a dict like:
      {"background": [{"scene_id": "s1", "matching_excerpt": "...relevant line..."}]}
    """
    evidence: dict[str, list[dict[str, str]]] = {}
    for field, value in proposed_fields.items():
        if not value:
            continue
        # Extract multi-word phrases only (3-5 word n-grams)
        # Do NOT match individual words — they cause false positives on contradictions
        # (e.g. "refuse de transmettre" matches "transmettre" alone)
        words = normalize(value).split()
        phrases = []
        for length in (5, 4, 3):
            for i in range(len(words) - length + 1):
                phrases.append(" ".join(words[i : i + length]))

        matches: list[dict[str, str]] = []
        for scene_id, raw_text in raw_texts:
            normalized_raw = normalize(raw_text)
            matched_phrases = [p for p in phrases if p in normalized_raw]
            if matched_phrases:
                # Find the most relevant line
                for line in raw_text.split("\n"):
                    if any(p in normalize(line) for p in matched_phrases):
                        matches.append({"scene_id": scene_id, "matching_excerpt": line.strip()})
                        break
                else:
                    matches.append({"scene_id": scene_id, "matching_excerpt": ", ".join(matched_phrases[:3])})
        evidence[field] = matches
    return evidence

ENTITY_CHECK_PROMPT = """\
You verify screenplay character profile edits against scene evidence.

INPUT:
- "character_id": the character being checked
- "proposed_changes": fields the author wants to modify
- "evidence": for each proposed field, a list of matching excerpts found in the original scene text. \
This was computed by text search — if a field has evidence entries, the proposed text IS in the scenes.
- "scene_fragments": scenes with "raw_text" for additional context

DECISION PROCESS:
1. Check "evidence" for each proposed field.
2. If evidence[field] is NOT EMPTY → the proposed change is SUPPORTED by scenes → no issue.
3. If evidence[field] IS EMPTY → check if the proposed text contradicts any raw_text \
(profile_contradiction) or is a specific unsupported claim (missing_evidence).
4. When in doubt → no issue.

CRITICAL: If a field has entries in "evidence", it means the text was found in scenes. Do NOT report it.

EXAMPLES:

Example 1 — HAS EVIDENCE (return issues=[]):
proposed background: "Meteorologue en poste sur la station Boreos-4"
evidence.background: [{"scene_id": "s1", "matching_excerpt": "Ravi Okonkwo, meteorologue en poste"}]
→ Text found in scene → SUPPORTED → issues=[]

Example 2 — CONTRADICTION (return 1 issue):
proposed arc: "Ravi refuse de lancer l'alerte cyclone"
evidence.arc: [] (empty)
raw_text says: "Il declencha l'alerte." (he triggered the alert)
→ Proposed says he refused, scene says he triggered → profile_contradiction

Example 3 — UNSUPPORTED (return 1 issue):
proposed background: "Decorated veteran of the Mars campaign"
evidence.background: [] (empty)
No raw_text mentions Mars or military.
→ missing_evidence

OUTPUT FORMAT for each issue:
- type: "profile_contradiction" or "missing_evidence"
- severity: "error" or "warning"
- scene_id: scene where contradiction is found (null for missing_evidence)
- entity_id: the character_id
- description: explain what contradicts or what is unsupported
- suggestion: how to fix
"""


async def check_character_consistency(
    driver: AsyncDriver,
    char_id: str,
    proposed_fields: dict[str, str | None],
    model_name: str | None = None,
    base_url: str | None = None,
) -> ConsistencyReport:
    """Check proposed profile changes against scene evidence."""
    profile = await get_character_profile(driver, char_id)
    if not profile:
        msg = f"Character {char_id} not found"
        raise ValueError(msg)

    relations = await get_character_relations(driver, char_id)
    fragments = await get_character_fragments(driver, char_id)

    scene_ids = [f["scene_id"] for f in fragments]
    summaries = await get_scene_summaries_by_ids(driver, scene_ids)
    summary_map = {s["id"]: s.get("summary", "") for s in summaries}

    # Fetch raw scene text for accurate checking
    raw_text_map: dict[str, str] = {}
    if scene_ids:
        async with driver.session() as session:
            result = await session.run(
                "MATCH (s:Scene) WHERE s.id IN $ids RETURN s.id AS id, s.raw_text AS raw_text",
                ids=scene_ids,
            )
            for record in await result.data():
                if record.get("raw_text"):
                    raw_text_map[record["id"]] = record["raw_text"]

    scene_data = [
        {
            "scene_id": f["scene_id"],
            "scene_title": f["scene_title"],
            "role": f["role"],
            "description": f["description"],
            "context": f["context"],
            "summary": summary_map.get(f["scene_id"], ""),
            "raw_text": raw_text_map.get(f["scene_id"], ""),
        }
        for f in fragments
    ]

    # Pre-compute text evidence — fields with matches are supported, skip LLM for those
    raw_texts = [(f["scene_id"], raw_text_map.get(f["scene_id"], "")) for f in fragments]
    evidence = _find_evidence(proposed_fields, raw_texts)

    # Only send unsupported fields to the LLM
    unsupported_fields = {
        field: value
        for field, value in proposed_fields.items()
        if value and not evidence.get(field)
    }

    # If all fields are supported by text evidence, no need to call the LLM
    if not unsupported_fields:
        return ConsistencyReport(issues=[])

    payload = {
        "character_id": char_id,
        "current_profile": {
            k: v
            for k, v in profile.items()
            if k in ("name", "age", "physical", "background", "arc", "traits", "era")
        },
        "proposed_changes": unsupported_fields,
        "relations": [
            {"other_name": r["other_name"], "relation_type": r["relation_type"]}
            for r in relations
        ],
        "scene_fragments": scene_data,
    }

    model = build_model(model_name, base_url)
    agent: Agent[None, ConsistencyReport] = Agent(
        model,
        instructions=ENTITY_CHECK_PROMPT,
        output_type=ConsistencyReport,
        model_settings=ModelSettings(temperature=0.1),
        retries=2,
    )

    result = await agent.run(json.dumps(payload, ensure_ascii=False, indent=2))
    return result.output
