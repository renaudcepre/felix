from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.mistral import MistralProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings


class _OpenRouterTransport(httpx.AsyncBaseTransport):
    """Injecte provider.require_parameters=true dans les requêtes OpenRouter."""

    def __init__(self) -> None:
        self._inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        ct = request.headers.get("content-type", "")
        if ct.startswith("application/json"):
            body = json.loads(request.content)
            if "messages" in body:
                if body.get("tool_choice") == "required":
                    body["tool_choice"] = "auto"
                new_content = json.dumps(body).encode()
                headers = {
                    k: v for k, v in request.headers.items()
                    if k.lower() != "content-length"
                }
                request = httpx.Request(
                    method=request.method,
                    url=request.url,
                    headers=headers,
                    content=new_content,
                )
        return await self._inner.handle_async_request(request)

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

EXAMPLE: "Qui est au poste de relais ?"
1. find_location("poste de relais") → details du lieu
2. get_timeline(location="poste de relais") → evenements et personnages presents
3. Synthetiser en citant les sources.
"""


def _build_model(
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> Model:
    name = model_name or settings.llm_model
    url = base_url or settings.llm_base_url

    if url:
        is_openrouter = "openrouter" in url
        is_together = "together" in url
        if is_openrouter:
            key = api_key or settings.open_router_key or "lm-studio"
            http_client = httpx.AsyncClient(transport=_OpenRouterTransport())
            openai_client = AsyncOpenAI(base_url=url, api_key=key, http_client=http_client)
            return OpenAIModel(name, provider=OpenAIProvider(openai_client=openai_client))
        if is_together:
            key = api_key or settings.together_key or "lm-studio"
        else:
            key = api_key or settings.llm_api_key or "lm-studio"
        return OpenAIModel(
            name,
            provider=OpenAIProvider(base_url=url, api_key=key),
        )
    return MistralModel(
        name,
        provider=MistralProvider(api_key=settings.llm_api_key),
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
