from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.ingest.models import CharacterProfile, NarrativeBeat
from felix.llm import build_model

if TYPE_CHECKING:
    from pydantic_ai.models import Model

logger = logging.getLogger("felix.ingest.profiler")

PROFILER_PATCH_PROMPT = """\
You update a character profile with information from a new scene.

Return the COMPLETE updated profile: keep all existing info, add what the new scene reveals. \
One concise sentence per field. Use null for unknown fields.

Every field describes THIS character only — ignore other characters' attributes even if mentioned \
in the same scene. Use only the "Events involving" section for arc if present.

Relations must describe a real bond (mentor, rival, ally). Mere co-presence in a scene is not a relation.
"""

PROFILER_PROMPT = """\
You synthesize a character profile from screenplay excerpts. Write only facts stated in the text. \
Use null for anything not explicitly mentioned.

Fields:
- age: only if the text states it ("She was forty-five" → "45"). Duration of service is not age.
- physical: permanent appearance only (build, hair, scars). Exclude momentary states.
- background: history and origins from the text.
- arc: what this character does across scenes. Use the "Events involving" section if present.
- traits: personality shown through actions and dialogue.
- relations: real bonds only (mentor, rival, ally, family). Co-presence is not a relation.

One sentence per field. Describe THIS character only.
"""

BEAT_EXTRACTOR_PROMPT = """\
Extract narrative beats from a screenplay scene.
A beat = one action or event: who does what to whom.

Output format: a list of {subject, action, object} where object is null if nobody receives the action.
Use names exactly as they appear in the text.

Active characters are provided as a hint. Any character in the scene can be subject — \
including enemies, creatures, or unnamed figures — as long as an active character is subject or object.

Example scene:
  The guard grabs Nadia by the arm. She breaks free and runs. Tomasz watches from the doorway.

Example output:
  {subject: "the guard", action: "grabs by the arm", object: "Nadia"}
  {subject: "Nadia", action: "breaks free and runs", object: null}
  {subject: "Tomasz", action: "watches from the doorway", object: null}

Extract all significant physical actions and decisions. Ignore atmosphere and setting description.
"""


def create_profiler_agent(
    model_name: str | None = None, base_url: str | None = None
) -> Agent[None, CharacterProfile]:
    model: Model = build_model(model_name, base_url)
    return Agent(
        model,
        instructions=PROFILER_PROMPT,
        output_type=CharacterProfile,
        model_settings=ModelSettings(temperature=0.1),
        retries=2,
    )


RELATION_DEDUP_PROMPT = """\
You are checking if two relationship descriptions refer to the same relationship.

You receive:
- Character A and Character B names
- An existing relation already stored in the database
- A new candidate relation to potentially add
- The current profile of Character A (background and arc) for context

Answer with exactly one word:
- "merge" if the candidate describes the same relationship as the existing one (same nature, same bond)
- "keep_both" if they describe clearly distinct aspects worth preserving
- "unsure" if you cannot confidently decide — they might overlap but you are not certain

Examples:
  Existing: "companion met at the war council"
  Candidate: "ally forged through shared battle"
  → keep_both  (different moments, complementary aspects)

  Existing: "fellow traveler on the quest"
  Candidate: "companion on the quest to the Northern Wastes"
  → merge  (same relationship, different wording)

  Existing: "childhood friend"
  Candidate: "old acquaintance from the village"
  → unsure  (could be same bond or distinct relationships)

  Existing: "companion"
  Candidate: "travel companion"
  → merge  (same bond, the candidate just adds a generic qualifier)

  Existing: "ally in battle"
  Candidate: "ally"
  → merge  (same bond, one is more general than the other)

Output ONLY "merge", "keep_both", or "unsure". No explanation.
"""


def create_relation_dedup_agent(
    model_name: str | None = None, base_url: str | None = None
) -> Agent[None, str]:
    model: Model = build_model(model_name, base_url)
    return Agent(
        model,
        instructions=RELATION_DEDUP_PROMPT,
        output_type=str,
        model_settings=ModelSettings(temperature=0.0),
        retries=2,
    )


def create_beat_extractor_agent(
    model_name: str | None = None, base_url: str | None = None
) -> Agent[None, list[NarrativeBeat]]:
    model: Model = build_model(model_name, base_url)
    return Agent(
        model,
        instructions=BEAT_EXTRACTOR_PROMPT,
        output_type=list[NarrativeBeat],
        model_settings=ModelSettings(temperature=0.1),
        retries=2,
    )


def create_profiler_patch_agent(
    model_name: str | None = None, base_url: str | None = None
) -> Agent[None, CharacterProfile]:
    model: Model = build_model(model_name, base_url)
    return Agent(
        model,
        instructions=PROFILER_PATCH_PROMPT,
        output_type=CharacterProfile,
        model_settings=ModelSettings(temperature=0.1),
        retries=2,
    )


async def extract_scene_beats(
    agent: Agent[None, list[NarrativeBeat]],
    scene_text: str,
    character_names: list[str],
) -> list[NarrativeBeat]:
    prompt = f"Active characters: {', '.join(character_names)}\n\n{scene_text}"
    result = await agent.run(prompt)
    return result.output


async def patch_character_profile(
    agent: Agent[None, CharacterProfile],
    name: str,
    existing_profile: dict,
    new_scene_text: str,
    new_scene_fragment: dict,
    beats: list[NarrativeBeat] | None = None,
) -> CharacterProfile:
    parts = [f"Character: {name}\n"]
    parts.append("=== Current profile ===")
    for field in ("age", "physical", "background", "arc", "traits"):
        val = existing_profile.get(field)
        if val:
            parts.append(f"- {field}: {val}")

    role = new_scene_fragment.get("role", "")
    desc = new_scene_fragment.get("description", "")
    title = new_scene_fragment.get("scene_title") or new_scene_fragment.get("scene_id", "?")
    parts.append(f"\n=== New scene: '{title}' (role: {role}) ===")
    if desc:
        parts.append(f"Fragment: {desc}")

    if beats:
        parts.append(f"\n=== Events involving {name} ===")
        for b in beats:
            if b.object:
                parts.append(f"- {b.subject} → {b.action} → {b.object}")
            else:
                parts.append(f"- {b.subject} → {b.action}")

    parts.append(f"\n--- Scene text ---\n{new_scene_text}")

    input_text = "\n".join(parts)
    result = await agent.run(input_text)
    return result.output


async def profile_character(
    agent: Agent[None, CharacterProfile],
    name: str,
    scene_texts: list[str],
    fragments: list[dict],
    known_characters: list[str] | None = None,
    beats: list[NarrativeBeat] | None = None,
) -> CharacterProfile:
    parts = [f"Character: {name}\n"]
    for frag in fragments:
        title = frag.get("scene_title") or frag.get("scene_id", "?")
        role = frag.get("role", "")
        desc = frag.get("description", "")
        parts.append(f"- Scene '{title}' (role: {role}): {desc}")

    if known_characters:
        parts.append(f"\nKnown characters in the screenplay: {', '.join(known_characters)}")
        parts.append(
            "For relations, use the exact names from this list when possible."
        )

    if beats:
        parts.append(f"\n=== Events involving {name} ===")
        for b in beats:
            if b.object:
                parts.append(f"- {b.subject} → {b.action} → {b.object}")
            else:
                parts.append(f"- {b.subject} → {b.action}")

    parts.append("\nScene texts:")
    for i, text in enumerate(scene_texts, 1):
        parts.append(f"\n--- Scene {i} ---\n{text}")

    input_text = "\n".join(parts)
    result = await agent.run(input_text)
    return result.output
