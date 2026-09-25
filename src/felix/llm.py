"""LLM model builder — shared across chat agent and ingest pipeline."""
from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from mistralai import Mistral
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.mistral import MistralProvider
from pydantic_ai.providers.openai import OpenAIProvider

from felix.config import settings

if TYPE_CHECKING:
    from pydantic_ai.models import Model

# 90 s pour les LLM locaux lents ; évite les gels silencieux de 15 min
_HTTP_TIMEOUT = httpx.Timeout(90.0, connect=10.0)
# ⚠ Pour Mistral, le timeout du client httpx ne suffit PAS : le SDK mistralai
# pose `timeout=None` PAR REQUÊTE quand timeout_ms n'est pas configuré, et en
# httpx le timeout par requête ÉCRASE celui du client (vécu : 904 s d'attente
# sur un 504 du gateway Kong, x-kong-upstream-latency=900001). Le timeout doit
# passer par le canal que le SDK honore : timeout_ms. Gardé > 90 s du client
# httpx pour rester le seul à s'appliquer côté Mistral.
_MISTRAL_TIMEOUT_MS = 90_000


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
    # Client SDK construit NOUS-MÊMES pour porter timeout_ms (cf. commentaire
    # _MISTRAL_TIMEOUT_MS) — MistralProvider(api_key=…) ne l'expose pas.
    return MistralModel(
        name,
        provider=MistralProvider(
            mistral_client=Mistral(
                api_key=settings.llm_api_key,
                async_client=http_client,
                timeout_ms=_MISTRAL_TIMEOUT_MS,
            )
        ),
    )


def build_checker_model() -> Model:
    """Build model for the consistency checker (per-feature override)."""
    return build_model(settings.llm_checker_model, settings.llm_checker_base_url)


def build_chat_model() -> Model:
    """Build model for the chatbot (per-feature override)."""
    return build_model(settings.llm_chat_model, settings.llm_chat_base_url)


def build_gate_model() -> Model:
    """Build model for the routing gate (per-feature override, fallback chat).

    Le gate est le « petit truc simple » du tiering intra-famille : 1 appel
    court, stateless, sortie structurée binaire — premier candidat à descendre
    d'un tier (ex. Devstral Small 2) avec le modèle de chat en garant."""
    return build_model(
        settings.llm_gate_model or settings.llm_chat_model,
        settings.llm_gate_base_url if settings.llm_gate_model else settings.llm_chat_base_url,
    )


def build_verifier_model() -> Model:
    """Build model for the source verifier (per-feature override, fallback checker).

    Le vérificateur source relit le texte d'origine d'UNE alerte distincte
    (jamais par entité, cf. felix.atelier.pipeline.consistency_alerts) : un
    volume encore plus faible que le checker — un modèle dédié permet de
    monter en qualité sans toucher au budget des extracteurs, avec le checker
    en garant si aucun modèle dédié n'est configuré."""
    return build_model(
        settings.llm_verifier_model or settings.llm_checker_model,
        settings.llm_verifier_base_url if settings.llm_verifier_model else settings.llm_checker_base_url,
    )
