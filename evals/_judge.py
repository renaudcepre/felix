"""Judge LLM partagé entre les sessions d'evals (legacy + atelier)."""
from __future__ import annotations

from protest.evals import JudgeResponse
from pydantic_ai import Agent
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.providers.mistral import MistralProvider

from felix.config import settings

# Tarif Mistral Small ($/Mtok) — partagé avec le calcul de coût des tasks.
MISTRAL_SMALL_INPUT_COST = 0.10 / 1e6
MISTRAL_SMALL_OUTPUT_COST = 0.30 / 1e6


class FelixJudge:
    name = "mistral-small-latest"
    provider = "mistral"

    async def judge(self, prompt: str, output_type: type) -> JudgeResponse:
        model = MistralModel(
            "mistral-small-latest",
            provider=MistralProvider(api_key=settings.llm_api_key),
        )
        agent = Agent(model, output_type=output_type)
        result = await agent.run(prompt)
        usage = result.usage()
        in_tok, out_tok = usage.request_tokens or 0, usage.response_tokens or 0
        return JudgeResponse(
            output=result.output,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=in_tok * MISTRAL_SMALL_INPUT_COST + out_tok * MISTRAL_SMALL_OUTPUT_COST,
        )
