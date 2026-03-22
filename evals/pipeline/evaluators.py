"""Evaluators for the import pipeline eval suite."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals._utils import normalize
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
class SceneDateContainsKeywords(Evaluator[str, PipelineQueryResult]):
    """Check that the scene date contains expected keywords.

    expected_output: comma-separated keywords (partial match, lowercased).
    Example: "2157"
    """

    min_match: int = 1

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, float | str | bool]:
        if not ctx.expected_output:
            return {}
        keywords = [k.strip() for k in ctx.expected_output.split(",") if k.strip()]
        date_str = (ctx.output.scene_date or "").lower()
        matched = [k for k in keywords if k.lower() in date_str]
        score = len(matched) / len(keywords) if keywords else 1.0
        return {
            "date_score": score,
            "date_ok": len(matched) >= self.min_match,
            "date_matched": ", ".join(matched) if matched else "none",
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


@dataclass
class ExactFragmentCount(Evaluator[str, PipelineQueryResult]):
    """Check that fragment_count == expected (exact, not >=).

    expected_output: exact count as a string.
    Example: "1"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool | int]:
        expected = int(ctx.expected_output or 0)
        count = ctx.output.fragment_count
        return {"exact_fragments": count == expected, "fragments_got": count}


@dataclass
class RelationWithCharPresent(Evaluator[str, PipelineQueryResult]):
    """Check that a relation involving expected_output exists for the queried character.

    expected_output: slugified character ID to look for in relations.
    Example: "chen-wei"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool]:
        target = (ctx.expected_output or "").strip()
        found = any(r["a"] == target or r["b"] == target for r in ctx.output.relations)
        return {"relation_found": found}


@dataclass
class IssueDescriptionContains(Evaluator[str, PipelineQueryResult]):
    """Check that at least one issue description contains the keyword (accent-insensitive).

    expected_output: keyword to search for.
    Example: "yuna"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool]:
        kw = normalize(ctx.expected_output or "")
        found = any(kw in normalize(i.get("description", "")) for i in ctx.output.issues)
        return {"issue_desc_match": found}


@dataclass
class IssueTypePresent(Evaluator[str, PipelineQueryResult]):
    """Check that at least one issue has the expected type (partial match).

    expected_output: type substring to look for.
    Example: "timeline_inconsistency"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool]:
        kw = (ctx.expected_output or "").strip()
        found = any(kw in i.get("type", "") for i in ctx.output.issues)
        return {"issue_type_found": found}


@dataclass
class MaxIssueSeverityCount(Evaluator[str, PipelineQueryResult]):
    """Check that the number of issues with the given severity is <= expected_output.

    severity: the severity level to count (default "error").
    expected_output: max allowed count as a string.
    Example: "0"
    """

    severity: str = "error"

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool | int]:
        max_allowed = int(ctx.expected_output or 0)
        count = sum(1 for i in ctx.output.issues if i.get("severity") == self.severity)
        return {"severity_ok": count <= max_allowed, f"{self.severity}_count": count}


@dataclass
class IssueTypeAbsent(Evaluator[str, PipelineQueryResult]):
    """Check that NO issue has the expected type (partial match) — inverse of IssueTypePresent.

    expected_output: type substring that must NOT appear.
    Example: "timeline_inconsistency"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool]:
        kw = (ctx.expected_output or "").strip()
        found = any(kw in i.get("type", "") for i in ctx.output.issues)
        return {"issue_type_absent": not found}


@dataclass
class ExactIssueCountByType(Evaluator[str, PipelineQueryResult]):
    """Vérifie que le nombre d'issues d'un type donné est exactement N.

    expected_output: count exact en string. Ex: "3"
    """

    issue_type: str = "bilocalization"

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool | int]:
        expected = int(ctx.expected_output or 0)
        count = sum(1 for i in ctx.output.issues if i.get("type") == self.issue_type)
        return {"exact_type_count": count == expected, "type_count_got": count}


@dataclass
class NoIssueDescriptionContains(Evaluator[str, PipelineQueryResult]):
    """Vérifie qu'AUCUNE description d'issue ne contient le mot-clé (insensible accents).

    expected_output: mot-clé interdit. Ex: "anachronique"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool | str]:
        kw = normalize(ctx.expected_output or "")
        failing = [i.get("description", "") for i in ctx.output.issues
                   if kw in normalize(i.get("description", ""))]
        result: dict[str, bool | str] = {"no_desc_match": not failing}
        if failing:
            result["offending_desc"] = failing[0][:80]
        return result


@dataclass
class ProfileNotContainsKeyword(Evaluator[str, PipelineQueryResult]):
    """Check that the character profile does NOT contain a keyword (attribution test).

    expected_output: comma-separated keywords, ALL must be absent.
    Example: "morgul,poignard,lame"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool | str]:
        if not ctx.expected_output:
            return {}
        keywords = [k.strip().lower() for k in ctx.expected_output.split(",") if k.strip()]
        bg = (ctx.output.background or "").lower()
        found = [k for k in keywords if k in bg]
        result: dict[str, bool | str] = {"profile_not_contains": not found}
        if found:
            result["found_keywords"] = ", ".join(found)
        return result


@dataclass
class MinChunkCount(Evaluator[str, PipelineQueryResult]):
    """Check that a file was segmented into at least N chunks (Scene nodes).

    expected_output: minimum chunk count as a string.
    Example: "2"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool | int]:
        expected = int(ctx.expected_output or 1)
        count = ctx.output.fragment_count
        return {"chunks_ok": count >= expected, "chunks_got": count}


@dataclass
class GroupIdsPresent(Evaluator[str, PipelineQueryResult]):
    """Check that all expected group IDs are present in the Group nodes.

    expected_output: comma-separated slugified group IDs.
    Example: "les-drones,les-pillards"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, float | str]:
        if not ctx.expected_output:
            return {}
        expected = {s.strip() for s in ctx.expected_output.split(",")}
        found = set(ctx.output.group_ids)
        present = expected & found
        missing = expected - found
        score = len(present) / len(expected) if expected else 1.0
        result: dict[str, float | str] = {"group_id_recall": score}
        if missing:
            result["missing_group_ids"] = ", ".join(sorted(missing))
        return result


@dataclass
class GroupAbsent(Evaluator[str, PipelineQueryResult]):
    """Check that an ID is NOT in the group_ids list (negative test).

    expected_output: slugified ID that must not be a Group.
    Example: "pixel"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool]:
        target = (ctx.expected_output or "").strip()
        found = target in ctx.output.group_ids
        return {"group_absent_pass": not found}


@dataclass
class RelationTextNotContainsKeyword(Evaluator[str, PipelineQueryResult]):
    """Check that NO relation text contains any of the expected keywords (co-presence filter).

    expected_output: comma-separated keywords, ALL must be absent from all relation texts.
    Example: "present,participant,scene,together"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool | str]:
        if not ctx.expected_output:
            return {}
        keywords = [k.strip().lower() for k in ctx.expected_output.split(",") if k.strip()]
        relations = ctx.output.relations
        found: list[str] = []
        for r in relations:
            text = (r.get("relation") or "").lower()
            for kw in keywords:
                if kw in text:
                    found.append(f"{kw} in '{r.get('relation')}'")
        result: dict[str, bool | str] = {"no_copresence": not found}
        if found:
            result["offending_relations"] = "; ".join(found[:3])
        return result


@dataclass
class MaxRelationCount(Evaluator[str, PipelineQueryResult]):
    """Check that the relation count for a pair is at most N (dedup test).

    expected_output: max allowed count as a string.
    Example: "2"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool | int]:
        max_count = int(ctx.expected_output or 1)
        count = ctx.output.fragment_count
        return {"dedup_ok": count <= max_count, "relation_count_got": count}


@dataclass
class AllLocationsContainKeyword(Evaluator[str, PipelineQueryResult]):
    """Check that ALL locations contain the expected keyword (tests deduplication).

    expected_output: keyword all location names must contain.
    Example: "helios"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, PipelineQueryResult]
    ) -> dict[str, bool | str]:
        kw = (ctx.expected_output or "").strip().lower()
        names = ctx.output.location_names
        all_match = all(kw in n.lower() for n in names) if names else False
        failing = [n for n in names if kw not in n.lower()]
        result: dict[str, bool | str] = {"all_locations_match": all_match}
        if failing:
            result["locations_not_matching"] = ", ".join(failing)
        return result
