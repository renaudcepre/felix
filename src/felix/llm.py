"""LLM model builder — shared across chat agent and ingest pipeline."""
from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.mistral import MistralProvider
from pydantic_ai.providers.openai import OpenAIProvider

from felix.config import settings

if TYPE_CHECKING:
    from pydantic_ai.models import Model

# 90 s pour les LLM locaux lents ; évite les gels silencieux de 15 min
_HTTP_TIMEOUT = httpx.Timeout(90.0, connect=10.0)


def build_model(
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> Model:
    name = model_name or settings.llm_model
    url = base_url if base_url is not None else settings.llm_base_url

    # Mistral models use native API, not OpenAI-compatible
    if name.startswith("mistral-") and url and "mistral" not in url:
        url = None

    http_client = httpx.AsyncClient(timeout=_HTTP_TIMEOUT)

    if url:
        is_together = "together" in url
        is_openrouter = "openrouter" in url
        if is_together:
            key = api_key or settings.together_key
        elif is_openrouter:
            key = api_key or settings.openrouter_key
        else:
            key = api_key or settings.llm_api_key or "lm-studio"
        return OpenAIModel(
            name,
            provider=OpenAIProvider(base_url=url, api_key=key, http_client=http_client),
        )
    return MistralModel(
        name,
        provider=MistralProvider(api_key=settings.llm_api_key, http_client=http_client),
    )


def build_checker_model() -> Model:
    """Build model for the consistency checker (per-feature override)."""
    return build_model(settings.llm_checker_model, settings.llm_checker_base_url)


def build_chat_model() -> Model:
    """Build model for the chatbot (per-feature override)."""
    return build_model(settings.llm_chat_model, settings.llm_chat_base_url)
