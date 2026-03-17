"""Evaluators for the Felix chat agent eval suite."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals._utils import normalize


@dataclass
class ContainsExpectedFacts(Evaluator[str, str]):
    """Check that the response contains at least min_score fraction of expected keywords.

    expected_output: comma-separated keywords (partial match, accent-insensitive).
    Example: "Marie, Resistance, 1940s, coursiere"
    """

    min_score: float = 0.5

    def evaluate(self, ctx: EvaluatorContext[str, str]) -> dict[str, float | str | bool]:
        if not ctx.expected_output:
            return {}
        keywords = [k.strip() for k in ctx.expected_output.split(",") if k.strip()]
        output = normalize(ctx.output)
        matched = [k for k in keywords if normalize(k) in output]
        score = len(matched) / len(keywords) if keywords else 1.0
        result: dict[str, float | str | bool] = {
            "facts_score": score,
            "facts_ok": score >= self.min_score,
        }
        missing = [k for k in keywords if normalize(k) not in output]
        if missing:
            result["missing_facts"] = ", ".join(missing)
        return result


@dataclass
class RefusesToFabricate(Evaluator[str, str]):
    """Check that the response admits not knowing rather than fabricating.

    Used for negative tests where expected_output is empty.
    Passes if the response contains a refusal marker.
    """

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

    def evaluate(self, ctx: EvaluatorContext[str, str]) -> dict[str, bool]:
        output = normalize(ctx.output)
        refused = any(marker in output for marker in self._REFUSAL_MARKERS)
        return {"refused_to_fabricate": refused}
