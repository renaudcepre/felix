from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.llm import build_model

if TYPE_CHECKING:
    from pydantic_ai.models import Model

CLEANER_PROMPT = """\
You filter screenplay text by removing obvious filler. Keep all dialogue, names, dates, \
relationships, plot actions, and biographical details. Remove only isolated gestures \
("He nods.", "Silence.") and camera directions ("CUT TO:"). When in doubt, keep the line. \
Output the cleaned text directly, preserving the original language.
"""


def create_cleaner_agent(
    model_name: str | None = None, base_url: str | None = None
) -> Agent[None, str]:
    model: Model = build_model(model_name, base_url)
    return Agent(
        model,
        instructions=CLEANER_PROMPT,
        output_type=str,
        model_settings=ModelSettings(temperature=0.0),
    )


async def clean_scene_text(agent: Agent[None, str], scene_text: str) -> str:
    result = await agent.run(scene_text)
    return result.output
