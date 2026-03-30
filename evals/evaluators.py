"""Shared evaluators for the Felix eval suites."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from pydantic_ai import Agent
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.providers.mistral import MistralProvider
from protest.evals import EvalContext, Metric, Reason, Verdict, evaluator

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


@dataclass
class FactsResult:
    facts_score: Annotated[float, Metric]
    facts_ok: Annotated[bool, Verdict]
    missing_facts: Annotated[str, Reason] = ""


@evaluator
def contains_expected_facts(ctx: EvalContext, min_score: float = 0.5) -> FactsResult:
    if not ctx.expected_output:
        return FactsResult(facts_score=1.0, facts_ok=True)
    keywords = [k.strip() for k in ctx.expected_output.split(",") if k.strip()]
    output = normalize(ctx.output)
    matched = [k for k in keywords if normalize(k) in output]
    score = len(matched) / len(keywords) if keywords else 1.0
    missing = [k for k in keywords if normalize(k) not in output]
    return FactsResult(
        facts_score=score,
        facts_ok=score >= min_score,
        missing_facts=", ".join(missing) if missing else "",
    )


@dataclass
class LLMJudgeResult:
    LLMJudge: Annotated[bool, Verdict]
    reason: Annotated[str, Reason] = ""


@evaluator
async def llm_judge(ctx: EvalContext, rubric: str = "") -> LLMJudgeResult:
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
    text = result.output or ""
    passed = "pass" in text.lower().split()[0] if text.strip() else False
    return LLMJudgeResult(LLMJudge=passed, reason=text[:200])


@evaluator
def refuses_to_fabricate(ctx: EvalContext) -> bool:
    output = normalize(ctx.output)
    return any(marker in output for marker in _REFUSAL_MARKERS)
