from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.settings import ModelSettings

from felix.agent.chat_agent import _build_model
from felix.ingest.models import ExtractedCharacter, ExtractedLocation, SceneAnalysis

if TYPE_CHECKING:
    from pydantic_ai.models import Model

logger = logging.getLogger("felix.ingest.analyzer")


class _SceneMeta(BaseModel):
    title: str
    summary: str
    era: str
    approximate_date: str | None = None
    location: ExtractedLocation
    mood: str | None = None


META_PROMPT = """\
You are a specialized assistant for analyzing screenplay scenes.

From the scene text, extract the following information:
- title : short title (max 10 words)
- summary : 2-3 sentence summary
- era : decade-level period ("2050s", "2140s", "1940s", etc.)
- approximate_date : partial date extracted strictly from the text. \
Use YYYY if only the year is known. Use YYYY-MM if year and month are known. Use YYYY-MM-DD only if a full date is explicitly stated. \
NEVER invent a month or day that is not in the text. Return null only if there is NO temporal indication.
- location : main location of the scene with description if present
- mood : general atmosphere in one word or short phrase

RULES:
- Invent NOTHING. Extract only what is in the text.
- If information is not in the text, use null.
"""

CHARACTER_PROMPT = """\
You are a specialized assistant for extracting characters from screenplay scenes.

Extract ALL characters from the scene text, including those merely evoked or mentioned in passing:
- "participant" : the character PHYSICALLY ACTS in the scene (speaks, moves, does something)
- "witness" : the character is PRESENT in the scene but does not act directly
- "mentioned" : the character is EVOKED by another, in dialogue, narration, or a memory — even briefly. Includes ancestors, parents, people referenced by name.

IMPORTANT: if a character is named even ONCE in the text (e.g. "Elias's son", "as Jakes used to say"), they MUST appear in the list with the role "mentioned".

A character who is an ancestor, a parent, a memory, or who is spoken of in the past tense is "mentioned", NOT "participant".

CHARACTER NAMES:
- Use ONLY the character's proper name (first name + last name).
- Do NOT put title, profession, or rank in the "name" field \
(not "Doctor Jean Martin" but "Jean Martin", not "Captain Korvin" but "Lara Korvin").
- Profession or rank should go in the "description" field, not "name".
- EXCEPTION: creatures, monsters, or unnamed entities that physically act in the scene \
(attack, speak, move) ARE characters. Use their species/type as the name \
(e.g. "the creature", "the guard", "the android"). Do NOT omit them because they lack a human name.

PHYSICAL DESCRIPTION:
- Only include traits that are permanent or stable characteristics (e.g. height, build, age, scars, hair color, distinctive features).
- Do NOT include ephemeral or momentary states: fatigue, red eyes, tears, posture at a given moment, \
actions performed in the scene ("hand on the wheel", "sitting", "bleeding").
- If no permanent physical trait is mentioned, leave description null or describe only role/profession.

SCENE CONTEXT (separate from physical description):
- Summarize what this character DOES in this scene: key actions, dialogue topics, interactions with others.
- This field is used for entity disambiguation — it should help distinguish two characters with similar names.
- Keep it to 1-2 sentences max.
- If the character is only "mentioned" with no scene actions, use their mention context.

Examples:
  Character "Voss" in a cockpit scene → context: "Pilots the ship through the asteroid field, argues with Elena about the route"
  Character "Marcus" mentioned in dialogue → context: "Mentioned by Lena as the doctor who treated her wounds on Titan"
  Character "Elena" witnessing a fight → context: "Watches the confrontation between Voss and the guards from the corridor"
  Character "Old Tom" mentioned in passing → context: "Mentioned by Sarah as her late grandfather who built the cabin"

CHARACTER TYPE:
- "individual": any entity with a unique proper name, OR an unnamed entity acting alone
  ("the guard", "the creature", "the android"). Default.
- "group": a collective that refers to multiple entities simultaneously:
  factions, armies, species, organizations, unnamed collectives
  ("the orcs", "the Nazgûl", "the Fellowship", "the drones", "the guards").
  Use "group" when the name is inherently plural or refers to a collective force.

Examples:
  "Pixel" (named drone) → individual
  "the drones" → group
  "the Fellowship of the Ring" → group
  "a Black Rider" → individual  (one Nazgûl acting alone)
  "the Nazgûl" → group

RULES:
- Invent NOTHING. Extract only what is in the text.
- If information is not in the text, use null.
- Each character must appear ONLY ONCE in the list.
"""


@dataclass
class AnalyzerAgents:
    meta: Agent[None, _SceneMeta]
    characters: Agent[None, list[ExtractedCharacter]]


def create_analyzer_agent(
    model_name: str | None = None, base_url: str | None = None
) -> AnalyzerAgents:
    model: Model = _build_model(model_name, base_url)

    meta_agent: Agent[None, _SceneMeta] = Agent(
        model,
        instructions=META_PROMPT,
        output_type=_SceneMeta,
        model_settings=ModelSettings(temperature=0.1),
        retries=2,
    )

    char_agent: Agent[None, list[ExtractedCharacter]] = Agent(
        model,
        instructions=CHARACTER_PROMPT,
        output_type=list[ExtractedCharacter],
        model_settings=ModelSettings(temperature=0.1),
        retries=2,
    )

    @char_agent.output_validator
    def validate_characters(output: list[ExtractedCharacter]) -> list[ExtractedCharacter]:
        if len(output) < 1:
            raise ModelRetry("The scene must contain at least one character")
        return output

    return AnalyzerAgents(meta=meta_agent, characters=char_agent)


async def analyze_scene(
    agents: AnalyzerAgents, scene_text: str
) -> SceneAnalysis:
    meta_result, char_result = await asyncio.gather(
        agents.meta.run(scene_text),
        agents.characters.run(scene_text),
    )
    m = meta_result.output
    return SceneAnalysis(
        title=m.title,
        summary=m.summary,
        era=m.era,
        approximate_date=m.approximate_date,
        characters=char_result.output,
        location=m.location,
        mood=m.mood,
    )
