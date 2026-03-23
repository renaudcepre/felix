"""LLM model builder — shared across chat agent and ingest pipeline."""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.mistral import MistralProvider
from pydantic_ai.providers.openai import OpenAIProvider

from felix.config import settings

if TYPE_CHECKING:
    from pydantic_ai.models import Model


def build_model(
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> Model:
    name = model_name or settings.llm_model
    url = base_url if base_url is not None else settings.llm_base_url

    if url:
        is_together = "together" in url
        key = api_key or (settings.together_key if is_together else settings.llm_api_key) or "lm-studio"
        return OpenAIModel(
            name,
            provider=OpenAIProvider(base_url=url, api_key=key),
        )
    return MistralModel(
        name,
        provider=MistralProvider(api_key=settings.llm_api_key),
    )
