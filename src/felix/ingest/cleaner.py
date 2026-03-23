from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.llm import build_model

if TYPE_CHECKING:
    from pydantic_ai.models import Model

CLEANER_PROMPT = """\
You are a screenplay text filter. Your job is to remove only the most obvious filler lines, \
so that the cleaned text is easier to analyze for a language model with a limited context window.

REMOVE only lines that are ENTIRELY filler with absolutely no character or story information:
- Isolated physical gestures with no other content: "He nods.", "She smiles.", "He shrugs.", "Silence."
- Camera or technical directions: "CUT TO:", "FADE IN:", "CLOSE ON:"

KEEP everything else, especially:
- All dialogue (every line spoken by a character)
- Scene headings
- Any line mentioning a character's name, role, profession, or family relationship
- Any line containing durations, dates, career facts, or biographical details:
  Example: "It's the first time in eighteen months that..." → KEEP
  Example: "In fifteen years of career she had never seen..." → KEEP
  Example: "Priya adjusts a panel when her sister enters the room." → KEEP (introduces a relationship)
- Actions that advance the plot or reveal character motivation
- Any action involving conflict, decision, revelation, or relationship

When in doubt, KEEP the line. It is better to keep a filler line than to remove a line with character information.

OUTPUT the cleaned text directly, preserving the original language (French or other). \
Do not summarize, do not translate, do not add anything.
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
