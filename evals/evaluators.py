"""Shared evaluators for the Felix eval suites."""
from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.providers.mistral import MistralProvider
from protest.evals import EvalContext, evaluator

from evals._utils import normalize
from felix.config import settings

_REFUSAL_MARKERS = [
    "je ne trouve pas",
    "je n'ai pas",
    "pas d'information",
    "aucune information",
    "n'est pas mentionn",
    "introuvable",
    "ne figure pas",
    "pas dans",
    "aucune mention",
]


@evaluator
def contains_expected_facts(ctx: EvalContext, min_score: float = 0.5) -> dict:
    """Check that the response contains at least min_score fraction of expected keywords."""
    if not ctx.expected_output:
        return {}
    keywords = [k.strip() for k in ctx.expected_output.split(",") if k.strip()]
    output = normalize(ctx.output)
    matched = [k for k in keywords if normalize(k) in output]
    score = len(matched) / len(keywords) if keywords else 1.0
    result: dict = {"facts_score": score, "facts_ok": score >= min_score}
    missing = [k for k in keywords if normalize(k) not in output]
    if missing:
        result["missing_facts"] = ", ".join(missing)
    return result


@evaluator
async def llm_judge(ctx: EvalContext, rubric: str = "") -> dict:
    """LLM-based judge using Mistral Small."""
    model = MistralModel(
        "mistral-small-latest",
        provider=MistralProvider(api_key=settings.llm_api_key),
    )
    agent: Agent[None, str] = Agent(model, output_type=str)
    prompt = (
        f"Evaluate this response against the criteria below.\n\n"
        f"Question: {ctx.inputs}\n"
        f"Response: {ctx.output}\n"
        f"Criteria: {rubric}\n\n"
        f"Answer ONLY 'PASS' or 'FAIL' followed by a brief reason."
    )
    result = await agent.run(prompt)
    passed = "pass" in result.output.lower().split()[0] if result.output else False
    return {"LLMJudge": passed}


@evaluator
def refuses_to_fabricate(ctx: EvalContext) -> dict:
    """Check that the response admits not knowing rather than fabricating."""
    output = normalize(ctx.output)
    refused = any(marker in output for marker in _REFUSAL_MARKERS)
    return {"refused_to_fabricate": refused}
