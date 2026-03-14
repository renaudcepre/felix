from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.mistral import MistralProvider
from pydantic_ai.providers.openai import OpenAIProvider

if TYPE_CHECKING:
    from pydantic_ai.models import Model

from felix.agent.deps import FelixDeps
from felix.agent.tools import (
    find_character,
    find_location,
    get_timeline,
    search_scenes,
)
from felix.config import settings

SYSTEM_PROMPT = """\
You are Felix, a screenplay continuity assistant for a French multi-era thriller.
You answer in French.

RULES:
1. ONLY answer based on information from your tools. Never invent facts.
2. If you don't find the information, say so clearly.

HOW TO ANSWER:
- To learn about a character, call find_character with their name.
- To learn about a location, call find_location with its name.
- To check events/timelines, call get_timeline with date filters (YYYY-MM-DD).
- To search scene content, call search_scenes with a description.
- Reason carefully and cite sources (profile, event, scene).

EXAMPLE: "Est-ce coherent si Marie rencontre Sarah en mars 1942 ?"
1. find_character("Marie") → profil
2. find_character("Sarah") → profil
3. get_timeline(date_from="1942-03-01", date_to="1942-03-31") → evenements
4. Raisonner sur la coherence.
"""


def _build_model(
    model_name: str | None = None, base_url: str | None = None
) -> Model:
    name = model_name or settings.felix_model
    url = base_url or settings.felix_base_url

    if url:
        return OpenAIModel(
            name,
            provider=OpenAIProvider(base_url=url, api_key="lm-studio"),
        )
    return MistralModel(
        name,
        provider=MistralProvider(api_key=settings.felix_api_key),
    )


def create_agent(
    model_name: str | None = None, base_url: str | None = None
) -> Agent[FelixDeps, str]:
    model = _build_model(model_name, base_url)

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
