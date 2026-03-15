"""Evaluators for the import pipeline eval suite."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals.pipeline.task import PipelineQueryResult


@dataclass
class CharacterIdsPresent(Evaluator[str, PipelineQueryResult]):
    """Check that all expected character IDs are present.

    expected_output: comma-separated slugified IDs.
    Example: "irina-voss,kofi-adu,chen-wei,yuna-park"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, float | str]:
        if not ctx.expected_output:
            return {}
        expected = {s.strip() for s in ctx.expected_output.split(",")}
        found = set(ctx.output.character_ids)
        present = expected & found
        missing = expected - found
        score = len(present) / len(expected) if expected else 1.0
        result: dict[str, float | str] = {"char_id_recall": score}
        if missing:
            result["missing_ids"] = ", ".join(sorted(missing))
        return result


@dataclass
class LocationContainsKeyword(Evaluator[str, PipelineQueryResult]):
    """Check that at least one location name contains the expected keyword.

    expected_output: a substring to look for (case-insensitive).
    Example: "helios"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool | str]:
        if not ctx.expected_output:
            return {}
        kw = ctx.expected_output.strip().lower()
        names = ctx.output.location_names
        found = any(kw in n.lower() for n in names)
        return {"location_match": found, "locations_got": str(names)}


@dataclass
class MinIssueCount(Evaluator[str, PipelineQueryResult]):
    """Check that at least N issues were detected.

    expected_output: minimum number of issues as a string.
    Example: "1"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool | int]:
        min_issues = int(ctx.expected_output or 1)
        count = len(ctx.output.issues)
        return {"issue_detected": count >= min_issues, "issue_count": count}


@dataclass
class BackgroundContainsKeywords(Evaluator[str, PipelineQueryResult]):
    """Check that the character background contains enough expected keywords.

    expected_output: comma-separated keywords (partial match, lowercased).
    Example: "quinze,15,carri,observ,spatial"
    """

    min_match: int = 2

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, float | str | bool]:
        if not ctx.expected_output:
            return {}
        keywords = [k.strip() for k in ctx.expected_output.split(",") if k.strip()]
        bg = (ctx.output.background or "").lower()
        matched = [k for k in keywords if k.lower() in bg]
        score = len(matched) / len(keywords) if keywords else 1.0
        return {
            "bg_score": score,
            "bg_ok": len(matched) >= self.min_match,
            "bg_matched": ", ".join(matched) if matched else "none",
        }


@dataclass
class MinRelationsCount(Evaluator[str, PipelineQueryResult]):
    """Check that at least N character relations were extracted.

    expected_output: minimum count as a string.
    Example: "1"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool | int]:
        min_count = int(ctx.expected_output or 1)
        count = len(ctx.output.relations)
        return {"relations_ok": count >= min_count, "relations_count": count}


@dataclass
class CharacterAbsent(Evaluator[str, PipelineQueryResult]):
    """Check that a character ID is NOT in the pipeline DB (negative test).

    expected_output: slugified character ID.
    Example: "mystery-stranger"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool]:
        target = (ctx.expected_output or "").strip()
        found = target in ctx.output.character_ids
        return {"absent_pass": not found}


@dataclass
class MinFragmentCount(Evaluator[str, PipelineQueryResult]):
    """Check that a character appears in at least N scenes.

    expected_output: minimum count as a string.
    Example: "3"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool | int]:
        expected = int(ctx.expected_output or 1)
        count = ctx.output.fragment_count
        return {"fragments_ok": count >= expected, "fragments_got": count}
