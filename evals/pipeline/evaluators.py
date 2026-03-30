"""Evaluators for the import pipeline eval suite."""
from __future__ import annotations

from dataclasses import dataclass

from protest.evals import EvalContext, evaluator

from evals._utils import normalize


# --- Extraction ---

@dataclass
class CharIdResult:
    char_id_recall: float
    all_found: bool
    missing_ids: str = ""


@evaluator
def character_ids_present(ctx: EvalContext, min_recall: float = 1.0) -> CharIdResult:
    if not ctx.expected_output:
        return CharIdResult(char_id_recall=1.0, all_found=True)
    expected = {s.strip() for s in ctx.expected_output.split(",")}
    found = set(ctx.output.character_ids)
    present = expected & found
    missing = expected - found
    recall = len(present) / len(expected) if expected else 1.0
    return CharIdResult(
        char_id_recall=recall,
        all_found=recall >= min_recall,
        missing_ids=", ".join(sorted(missing)) if missing else "",
    )


@evaluator
def location_contains_keyword(ctx: EvalContext) -> bool:
    if not ctx.expected_output:
        return True
    kw = ctx.expected_output.strip().lower()
    return any(kw in n.lower() for n in ctx.output.location_names)


@evaluator
def character_absent(ctx: EvalContext) -> bool:
    target = (ctx.expected_output or "").strip()
    return target not in ctx.output.character_ids


@dataclass
class GroupIdResult:
    group_id_recall: float
    all_found: bool
    missing_group_ids: str = ""


@evaluator
def group_ids_present(ctx: EvalContext, min_recall: float = 1.0) -> GroupIdResult:
    if not ctx.expected_output:
        return GroupIdResult(group_id_recall=1.0, all_found=True)
    expected = {s.strip() for s in ctx.expected_output.split(",")}
    found = set(ctx.output.group_ids)
    present = expected & found
    missing = expected - found
    recall = len(present) / len(expected) if expected else 1.0
    return GroupIdResult(
        group_id_recall=recall,
        all_found=recall >= min_recall,
        missing_group_ids=", ".join(sorted(missing)) if missing else "",
    )


@evaluator
def group_absent(ctx: EvalContext) -> bool:
    target = (ctx.expected_output or "").strip()
    return target not in ctx.output.group_ids


# --- Profiling ---

@dataclass
class BgResult:
    bg_score: float
    bg_ok: bool
    bg_matched: str = ""


@evaluator
def background_contains_keywords(ctx: EvalContext, min_match: int = 2) -> BgResult:
    if not ctx.expected_output:
        return BgResult(bg_score=1.0, bg_ok=True)
    keywords = [k.strip() for k in ctx.expected_output.split(",") if k.strip()]
    bg = (ctx.output.background or "").lower()
    matched = [k for k in keywords if k.lower() in bg]
    score = len(matched) / len(keywords) if keywords else 1.0
    return BgResult(
        bg_score=score,
        bg_ok=len(matched) >= min_match,
        bg_matched=", ".join(matched) if matched else "none",
    )


@dataclass
class ProfileNotContainsResult:
    profile_not_contains: bool
    found_keywords: str = ""


@evaluator
def profile_not_contains_keyword(ctx: EvalContext) -> ProfileNotContainsResult:
    if not ctx.expected_output:
        return ProfileNotContainsResult(profile_not_contains=True)
    keywords = [k.strip().lower() for k in ctx.expected_output.split(",") if k.strip()]
    bg = (ctx.output.background or "").lower()
    found = [k for k in keywords if k in bg]
    return ProfileNotContainsResult(
        profile_not_contains=not found,
        found_keywords=", ".join(found) if found else "",
    )


# --- Dates ---

@dataclass
class DateResult:
    date_score: float
    date_ok: bool
    date_matched: str = ""


@evaluator
def scene_date_contains_keywords(ctx: EvalContext, min_match: int = 1) -> DateResult:
    if not ctx.expected_output:
        return DateResult(date_score=1.0, date_ok=True)
    keywords = [k.strip() for k in ctx.expected_output.split(",") if k.strip()]
    date_str = (ctx.output.scene_date or "").lower()
    matched = [k for k in keywords if k.lower() in date_str]
    score = len(matched) / len(keywords) if keywords else 1.0
    return DateResult(
        date_score=score,
        date_ok=len(matched) >= min_match,
        date_matched=", ".join(matched) if matched else "none",
    )


# --- Relations ---

@dataclass
class RelationsResult:
    relations_score: float
    relations_ok: bool
    relations_count: int = 0


@evaluator
def min_relations_count(ctx: EvalContext, max_count: int = 30) -> RelationsResult:
    min_count = int(ctx.expected_output or 1)
    count = len(ctx.output.relations)
    if count < min_count:
        score = count / min_count
    elif count <= max_count:
        score = 1.0
    else:
        score = max(0.0, 1.0 - (count - max_count) / max_count)
    return RelationsResult(
        relations_score=round(score, 2),
        relations_ok=min_count <= count <= max_count,
        relations_count=count,
    )


@evaluator
def relation_with_char_present(ctx: EvalContext) -> bool:
    target = (ctx.expected_output or "").strip()
    return any(r["a"] == target or r["b"] == target for r in ctx.output.relations)


@evaluator
def relation_text_not_contains_keyword(ctx: EvalContext) -> bool:
    if not ctx.expected_output:
        return True
    keywords = [k.strip().lower() for k in ctx.expected_output.split(",") if k.strip()]
    for r in ctx.output.relations:
        text = (r.get("relation") or "").lower()
        if any(kw in text for kw in keywords):
            return False
    return True


@evaluator
def max_relation_count(ctx: EvalContext) -> bool:
    max_count = int(ctx.expected_output or 1)
    return ctx.output.fragment_count <= max_count


# --- Fragments ---

@dataclass
class FragmentResult:
    fragments_ok: bool
    fragments_got: int = 0


@evaluator
def min_fragment_count(ctx: EvalContext) -> FragmentResult:
    expected = int(ctx.expected_output or 1)
    count = ctx.output.fragment_count
    return FragmentResult(fragments_ok=count >= expected, fragments_got=count)


@evaluator
def exact_fragment_count(ctx: EvalContext) -> FragmentResult:
    expected = int(ctx.expected_output or 0)
    count = ctx.output.fragment_count
    return FragmentResult(fragments_ok=count == expected, fragments_got=count)


@evaluator
def min_chunk_count(ctx: EvalContext) -> FragmentResult:
    expected = int(ctx.expected_output or 1)
    count = ctx.output.fragment_count
    return FragmentResult(fragments_ok=count >= expected, fragments_got=count)


# --- Issues ---

@evaluator
def issue_type_present(ctx: EvalContext) -> bool:
    kw = (ctx.expected_output or "").strip()
    return any(kw in i.get("type", "") for i in ctx.output.issues)


@evaluator
def issue_type_absent(ctx: EvalContext) -> bool:
    kw = (ctx.expected_output or "").strip()
    return not any(kw in i.get("type", "") for i in ctx.output.issues)


@evaluator
def issue_description_contains(ctx: EvalContext) -> bool:
    kw = normalize(ctx.expected_output or "")
    return any(kw in normalize(i.get("description", "")) for i in ctx.output.issues)


@evaluator
def no_issue_description_contains(ctx: EvalContext) -> bool:
    kw = normalize(ctx.expected_output or "")
    return not any(kw in normalize(i.get("description", "")) for i in ctx.output.issues)


@dataclass
class IssueSeverityResult:
    severity_ok: bool
    error_count: int = 0


@evaluator
def max_issue_severity_count(ctx: EvalContext, severity: str = "error") -> IssueSeverityResult:
    max_allowed = int(ctx.expected_output or 0)
    count = sum(1 for i in ctx.output.issues if i.get("severity") == severity)
    return IssueSeverityResult(severity_ok=count <= max_allowed, error_count=count)


@evaluator
def exact_issue_count_by_type(ctx: EvalContext, issue_type: str = "bilocalization") -> bool:
    expected = int(ctx.expected_output or 0)
    count = sum(1 for i in ctx.output.issues if i.get("type") == issue_type)
    return count == expected


@evaluator
def all_locations_contain_keyword(ctx: EvalContext) -> bool:
    kw = (ctx.expected_output or "").strip().lower()
    names = ctx.output.location_names
    return all(kw in n.lower() for n in names) if names else False


@evaluator
def min_issue_count(ctx: EvalContext) -> bool:
    min_issues = int(ctx.expected_output or 1)
    return len(ctx.output.issues) >= min_issues


# --- Entity Check ---

@evaluator
def entity_check_has_issue_type(ctx: EvalContext) -> bool:
    kw = (ctx.expected_output or "").strip()
    return any(kw in i.get("type", "") for i in ctx.output.issues)


@evaluator
def entity_check_no_issues(ctx: EvalContext) -> bool:
    return len(ctx.output.issues) == 0


@evaluator
def entity_check_no_issue_about_entity(ctx: EvalContext) -> bool:
    kw = normalize(ctx.expected_output or "")
    return not any(
        kw in normalize(i.get("entity_id") or "") or kw in normalize(i.get("description") or "")
        for i in ctx.output.issues
    )
