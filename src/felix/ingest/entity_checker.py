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
You check if a character profile edit is CONTRADICTED by a scene.

A contradiction means: the scene explicitly says the OPPOSITE about this character.
"Not mentioned" is NOT a contradiction. The screenwriter can add whatever they want.

For each proposed change, answer: does any scene say the OPPOSITE about this character?
- YES → report the issue, quote the scene passage that says the opposite.
- NO → do not report. This includes: new details, rewordings, style changes, details about \
other characters, information in a different language that means the same thing.

ONLY check the character in "character_name". Ignore other characters in the scenes.

OUTPUT: list of issues. Empty list if no contradiction found.
Each issue needs:
- type: "profile_contradiction"
- severity: "error"
- scene_id: which scene
- entity_id: the character_id
- description: quote the exact scene passage that says the OPPOSITE
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

    # Show the LLM what changed: previous value → proposed value
    diff = {
        field: {"before": profile.get(field), "after": value}
        for field, value in unsupported_fields.items()
    }

    payload = {
        "character_id": char_id,
        "character_name": profile.get("name", char_id),
        "current_profile": {
            k: v
            for k, v in profile.items()
            if k in ("name", "age", "physical", "background", "arc", "traits", "era")
        },
        "proposed_changes": diff,
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
