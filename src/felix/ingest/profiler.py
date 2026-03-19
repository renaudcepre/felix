from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.agent.chat_agent import _build_model
from felix.ingest.models import CharacterProfile, NarrativeBeat

if TYPE_CHECKING:
    from pydantic_ai.models import Model

logger = logging.getLogger("felix.ingest.profiler")

PROFILER_PATCH_PROMPT = """\
You are a specialized assistant for maintaining screenplay character profiles.

You are given:
1. The current validated profile of a character (from previous scenes)
2. A new scene in which this character appears

Your task: return the COMPLETE updated profile, merging existing information with what the new scene reveals.

RULES:
- Incorporate ALL existing profile information — do not lose any detail already known.
- Add new information revealed by the current scene.
- If a field already has content, synthesize old and new into a single concise statement — no duplication, no repetition, no " | " separators.
- If the scene adds nothing new for a field, return the existing value unchanged.
- If a field is unknown in both the profile and the scene, return null.
- Invent nothing: every piece of information must be traceable to the profile or the scene text.

ATTRIBUTION RULE (when an "Events involving <character>" section is present):
- For `arc` and `background`: only use events where this character is explicitly listed as subject or object.
- Do NOT attribute to this character any event that happens to someone else in the scene, even if mentioned nearby.
- The scene text provides context (dialogue, atmosphere) — not additional events to attribute.

One sentence per field maximum. Be concise and factual.
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
- arc: narrative evolution of the character across scenes, based on their concrete actions.
  If an "Events involving <character>" section is present, use ONLY those events for arc — do not
  attribute events that happen to other characters, even if mentioned in the scene text.
- traits: character traits ONLY as demonstrated by actions and dialogue in the text
- relations: list of relationships with other characters observed in the texts.
  For each relation, provide:
  - other_name: the exact name of the character as it appears in the texts
  - relation: free-form description of the relationship (e.g. "colleague at Helios-3 relay", \
"mentor", "rival", "father", "companion AI"). Be precise and contextual.
  List only relationships clearly present in the texts.

Be concise and factual.
"""

BEAT_EXTRACTOR_PROMPT = """\
Extract narrative beats from a screenplay scene.
A beat = one action or event: who does what to whom.

Output format: a list of {subject, action, object} where object is null if nobody receives the action.
Use names exactly as they appear in the text.

Active characters are provided as a hint. Any character in the scene can be subject — \
including enemies, creatures, or unnamed figures — as long as an active character is subject or object.

Example scene:
  The guard grabs Elena by the arm. She breaks free and runs. Viktor watches from the doorway.

Example output:
  {subject: "the guard", action: "grabs by the arm", object: "Elena"}
  {subject: "Elena", action: "breaks free and runs", object: null}
  {subject: "Viktor", action: "watches from the doorway", object: null}

Extract all significant physical actions and decisions. Ignore atmosphere and setting description.
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


def create_beat_extractor_agent(
    model_name: str | None = None, base_url: str | None = None
) -> Agent[None, list[NarrativeBeat]]:
    model: Model = _build_model(model_name, base_url)
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
    model: Model = _build_model(model_name, base_url)
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
