"""Shared evaluators for the Felix eval suites."""
from __future__ import annotations

from protest.evals import EvalContext, evaluator

from evals._utils import normalize

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
def refuses_to_fabricate(ctx: EvalContext) -> dict:
    """Check that the response admits not knowing rather than fabricating."""
    output = normalize(ctx.output)
    refused = any(marker in output for marker in _REFUSAL_MARKERS)
    return {"refused_to_fabricate": refused}
