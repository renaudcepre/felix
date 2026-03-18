from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic_ai import Agent, ModelRetry
from pydantic_ai.settings import ModelSettings

from felix.agent.chat_agent import _build_model
from felix.ingest.models import SceneAnalysis

if TYPE_CHECKING:
    from pydantic_ai.models import Model

logger = logging.getLogger("felix.ingest.analyzer")

ANALYZER_PROMPT = """\
You are a specialized assistant for analyzing screenplay scenes.

From the scene text, extract the following information:
- title : short title (max 10 words)
- summary : 2-3 sentence summary
- era : decade-level period ("2050s", "2140s", "1940s", etc.)
- approximate_date : date in YYYY-MM-DD format if inferable from the text. \
If only the year is known, use YYYY-01-01. \
If the year and month are known, use YYYY-MM-01. Return null only if there is NO temporal indication.
- characters : list of characters with their role and description if present
- location : main location of the scene with description if present
- mood : general atmosphere in one word or short phrase

CHARACTERS — EXTRACT ALL CHARACTERS, including those merely evoked or mentioned in passing:
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

RULES:
- Invent NOTHING. Extract only what is in the text.
- If information is not in the text, use null.
- Each character must appear ONLY ONCE in the list.
"""


def create_analyzer_agent(
    model_name: str | None = None, base_url: str | None = None
) -> Agent[None, SceneAnalysis]:
    model: Model = _build_model(model_name, base_url)
    agent: Agent[None, SceneAnalysis] = Agent(
        model,
        instructions=ANALYZER_PROMPT,
        output_type=SceneAnalysis,
        model_settings=ModelSettings(temperature=0.1),
        retries=2,
    )

    @agent.output_validator
    def validate_output(output: SceneAnalysis) -> SceneAnalysis:
        if len(output.characters) < 1:
            raise ModelRetry("The scene must contain at least one character")
        return output

    return agent


async def analyze_scene(
    agent: Agent[None, SceneAnalysis], scene_text: str
) -> SceneAnalysis:
    result = await agent.run(scene_text)
    return result.output
