from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.agent.chat_agent import _build_model
from felix.ingest.models import CharacterProfile

if TYPE_CHECKING:
    from pydantic_ai.models import Model

logger = logging.getLogger("felix.ingest.profiler")

PROFILER_PATCH_PROMPT = """\
You are a specialized assistant for enriching screenplay character profiles.

You are given:
1. The current validated profile of a character (from previous scenes)
2. A new scene in which this character appears

Your task: enrich the profile ONLY with what this new scene adds.

ABSOLUTE RULE:
- Do not modify, erase, or rephrase anything that already exists in the profile.
- Invent nothing: every added piece of information must be pointable to the scene text.
- If the scene adds nothing new for a field, return null for that field.
- A null field means "unchanged", not "empty".

Fields to enrich (null if no new information):
- age: if the scene specifies or confirms the age (new details only)
- physical: if the scene describes physical appearance (new details only)
- background: if the scene reveals new elements of the character's past
- arc: if the scene develops the character (new concrete actions)
- traits: if the scene demonstrates new character traits
- relations: new relationships observed in THIS scene only

Be concise and factual.
"""

PROFILER_PROMPT = """\
You are a specialized assistant for synthesizing screenplay character profiles.

You are given a character's name and excerpts from scenes in which they appear.
Synthesize a structured profile based ONLY on what is EXPLICITLY \
written in the provided texts.

ABSOLUTE RULE: every piece of information you write MUST be traceable to \
a specific sentence in the texts. If you cannot cite the source sentence, \
set the field to null. A null field is ALWAYS preferable to an invention.

Do NOT infer, extrapolate, or embellish. No "probably", \
no "seems", no guessing about appearance, clothing, age \
or personality if the text does not mention it.

Fields to fill:
- age: age or age range ONLY if the text mentions it explicitly
- physical: physical description ONLY if the text describes appearance \
(clothing, features, build...). "stared at the screen" is NOT a physical description.
- background: history and origins — ONLY what the text says about the character's past
- arc: narrative evolution of the character across scenes, based on their concrete actions
- traits: character traits ONLY as demonstrated by actions and dialogue in the text
- relations: list of relationships with other characters observed in the texts.
  For each relation, provide:
  - other_name: the exact name of the character as it appears in the texts
  - relation: free-form description of the relationship (e.g. "colleague at Helios-3 relay", \
"mentor", "rival", "father", "companion AI"). Be precise and contextual.
  List only relationships clearly present in the texts.

Be concise and factual.
"""


def create_profiler_agent(
    model_name: str | None = None, base_url: str | None = None
) -> Agent[None, CharacterProfile]:
    model: Model = _build_model(model_name, base_url)
    return Agent(
        model,
        instructions=PROFILER_PROMPT,
        output_type=CharacterProfile,
        model_settings=ModelSettings(temperature=0.1),
        retries=2,
    )


def create_profiler_patch_agent(
    model_name: str | None = None, base_url: str | None = None
) -> Agent[None, CharacterProfile]:
    model: Model = _build_model(model_name, base_url)
    return Agent(
        model,
        instructions=PROFILER_PATCH_PROMPT,
        output_type=CharacterProfile,
        model_settings=ModelSettings(temperature=0.1),
        retries=2,
    )


async def patch_character_profile(
    agent: Agent[None, CharacterProfile],
    name: str,
    existing_profile: dict,
    new_scene_text: str,
    new_scene_fragment: dict,
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

    parts.append("\nScene texts:")
    for i, text in enumerate(scene_texts, 1):
        parts.append(f"\n--- Scene {i} ---\n{text}")

    input_text = "\n".join(parts)
    result = await agent.run(input_text)
    return result.output
