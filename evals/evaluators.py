"""Custom evaluators for Felix evals."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_evals.evaluators import Evaluator, EvaluatorContext


@dataclass
class ContainsExpectedFacts(Evaluator[str, str]):
    """Check that expected facts (keywords) appear in the agent response.

    expected_output on the Case must be a comma-separated string of keywords.
    """

    threshold: float = 0.5

    def evaluate(
        self, ctx: EvaluatorContext[str, str]
    ) -> dict[str, float | bool | str]:
        if not ctx.expected_output:
            return {}

        expected_facts = [
            f.strip() for f in ctx.expected_output.split(",") if f.strip()
        ]
        if not expected_facts:
            return {}

        output_lower = ctx.output.lower()
        found = {fact: fact.lower() in output_lower for fact in expected_facts}
        score = sum(found.values()) / len(found)
        missing = [f for f, present in found.items() if not present]

        return {
            "facts_score": score,
            "facts_pass": score >= self.threshold,
            "missing_facts": ", ".join(missing) if missing else "none",
        }


@dataclass
class RefusesToFabricate(Evaluator[str, str]):
    """Check that the agent refuses to answer when info is absent from the bible."""

    refusal_markers: list[str] = field(
        default_factory=lambda: [
            "pas dans la bible",
            "pas d'information",
            "je ne trouve pas",
            "aucune information",
            "not found",
            "no information",
            "don't have",
            "ne sais pas",
            "ne dispose pas",
            "n'est pas mentionn",
            "no mention",
            "not mention",
            "isn't mention",
            "no data",
            "aucune donnee",
            "pas de donnee",
        ]
    )

    def evaluate(self, ctx: EvaluatorContext[str, str]) -> bool:
        output_lower = ctx.output.lower()
        return any(marker in output_lower for marker in self.refusal_markers)
