from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.settings import ModelSettings

from felix.ingest.models import ExtractedCharacter, ExtractedLocation, SceneAnalysis
from felix.llm import build_model

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
You extract characters from screenplay scenes.

For each character found in the text, provide:
- name: proper name only ("Jean Martin", not "Doctor Jean Martin"). For unnamed entities use type ("the guard").
- role: "participant" (acts in scene), "witness" (present, passive), or "mentioned" (evoked in dialogue/narration).
- description: permanent physical traits only (height, hair, scars). Use null if none mentioned. Exclude momentary states (fatigue, posture).
- context: 1-2 sentences on what this character does or how they are referenced. Helps disambiguate similar names.
- character_type: "individual" (default) or "group" (plural collectives like "the guards", "the rebels").

Include every named person, even those only mentioned once in passing.
Each character appears only once. Extract only what the text states.
"""


@dataclass
class AnalyzerAgents:
    meta: Agent[None, _SceneMeta]
    characters: Agent[None, list[ExtractedCharacter]]


def create_analyzer_agent(
    model_name: str | None = None, base_url: str | None = None
) -> AnalyzerAgents:
    model: Model = build_model(model_name, base_url)

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
