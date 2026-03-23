from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.agent.deps import FelixDeps
from felix.agent.tools import (
    find_character,
    find_location,
    get_timeline,
    search_scenes,
)
from felix.llm import build_model

SYSTEM_PROMPT = """\
You are Felix, a screenplay continuity assistant for a French multi-era thriller.

RULES:
1. ONLY report information that comes directly from your tools. Never invent, complete, or elaborate beyond what the tools return.
2. If a tool returns no data, say "Je ne trouve pas cette information dans la bible." — do not guess.
3. Never ask the user for clarification. Always try the most likely tool call immediately.

HOW TO ANSWER:
- Character question → find_character(name)
- Location question → find_location(name)
- Who is at a location / what happens there → get_timeline(location="partial name")
- Events in a period → get_timeline(date_from=..., date_to=...)
- Scene content / dialogue → search_scenes(query)
- Combine tools when needed. Cite which tool returned each fact.

EXAMPLE: "Who is at the relay station?"
1. find_location("relay station") → location details
2. get_timeline(location="relay station") → events and characters present
3. Synthesize, citing which tool returned each fact.
"""


def create_agent(
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> Agent[FelixDeps, str]:
    model = build_model(model_name, base_url, api_key=api_key)

    agent = Agent(
        model,
        instructions=SYSTEM_PROMPT,
        deps_type=FelixDeps,
        output_type=str,
        model_settings=ModelSettings(temperature=0.1),
    )

    agent.tool(find_character)
    agent.tool(find_location)
    agent.tool(get_timeline)
    agent.tool(search_scenes)

    return agent
