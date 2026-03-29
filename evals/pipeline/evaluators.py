"""Evaluators for the import pipeline eval suite."""
from __future__ import annotations

from protest.evals import EvalContext, evaluator

from evals._utils import normalize


@evaluator
def character_ids_present(ctx: EvalContext) -> dict:
    if not ctx.expected_output:
        return {}
    expected = {s.strip() for s in ctx.expected_output.split(",")}
    found = set(ctx.output.character_ids)
    present = expected & found
    missing = expected - found
    score = len(present) / len(expected) if expected else 1.0
    result: dict = {"char_id_recall": score}
    if missing:
        result["missing_ids"] = ", ".join(sorted(missing))
    return result


@evaluator
def location_contains_keyword(ctx: EvalContext) -> dict:
    if not ctx.expected_output:
        return {}
    kw = ctx.expected_output.strip().lower()
    names = ctx.output.location_names
    found = any(kw in n.lower() for n in names)
    return {"location_match": found, "locations_got": str(names)}


@evaluator
def min_issue_count(ctx: EvalContext) -> dict:
    min_issues = int(ctx.expected_output or 1)
    count = len(ctx.output.issues)
    return {"issue_detected": count >= min_issues, "issue_count": count}


@evaluator
def background_contains_keywords(ctx: EvalContext, min_match: int = 2) -> dict:
    if not ctx.expected_output:
        return {}
    keywords = [k.strip() for k in ctx.expected_output.split(",") if k.strip()]
    bg = (ctx.output.background or "").lower()
    matched = [k for k in keywords if k.lower() in bg]
    score = len(matched) / len(keywords) if keywords else 1.0
    return {
        "bg_score": score,
        "bg_ok": len(matched) >= min_match,
        "bg_matched": ", ".join(matched) if matched else "none",
    }


@evaluator
def scene_date_contains_keywords(ctx: EvalContext, min_match: int = 1) -> dict:
    if not ctx.expected_output:
        return {}
    keywords = [k.strip() for k in ctx.expected_output.split(",") if k.strip()]
    date_str = (ctx.output.scene_date or "").lower()
    matched = [k for k in keywords if k.lower() in date_str]
    score = len(matched) / len(keywords) if keywords else 1.0
    return {
        "date_score": score,
        "date_ok": len(matched) >= min_match,
        "date_matched": ", ".join(matched) if matched else "none",
    }


@evaluator
def min_relations_count(ctx: EvalContext, max_count: int = 30) -> dict:
    min_count = int(ctx.expected_output or 1)
    count = len(ctx.output.relations)
    if count < min_count:
        score = count / min_count
    elif count <= max_count:
        score = 1.0
    else:
        score = max(0.0, 1.0 - (count - max_count) / max_count)
    return {"relations_ok": min_count <= count <= max_count, "relations_count": count, "relations_score": round(score, 2)}


@evaluator
def character_absent(ctx: EvalContext) -> dict:
    target = (ctx.expected_output or "").strip()
    found = target in ctx.output.character_ids
    return {"absent_pass": not found}


@evaluator
def min_fragment_count(ctx: EvalContext) -> dict:
    expected = int(ctx.expected_output or 1)
    count = ctx.output.fragment_count
    return {"fragments_ok": count >= expected, "fragments_got": count}


@evaluator
def exact_fragment_count(ctx: EvalContext) -> dict:
    expected = int(ctx.expected_output or 0)
    count = ctx.output.fragment_count
    return {"exact_fragments": count == expected, "fragments_got": count}


@evaluator
def relation_with_char_present(ctx: EvalContext) -> dict:
    target = (ctx.expected_output or "").strip()
    found = any(r["a"] == target or r["b"] == target for r in ctx.output.relations)
    return {"relation_found": found}


@evaluator
def issue_description_contains(ctx: EvalContext) -> dict:
    kw = normalize(ctx.expected_output or "")
    found = any(kw in normalize(i.get("description", "")) for i in ctx.output.issues)
    return {"issue_desc_match": found}


@evaluator
def issue_type_present(ctx: EvalContext) -> dict:
    kw = (ctx.expected_output or "").strip()
    found = any(kw in i.get("type", "") for i in ctx.output.issues)
    return {"issue_type_found": found}


@evaluator
def max_issue_severity_count(ctx: EvalContext, severity: str = "error") -> dict:
    max_allowed = int(ctx.expected_output or 0)
    count = sum(1 for i in ctx.output.issues if i.get("severity") == severity)
    return {"severity_ok": count <= max_allowed, f"{severity}_count": count}


@evaluator
def issue_type_absent(ctx: EvalContext) -> dict:
    kw = (ctx.expected_output or "").strip()
    found = any(kw in i.get("type", "") for i in ctx.output.issues)
    return {"issue_type_absent": not found}


@evaluator
def exact_issue_count_by_type(ctx: EvalContext, issue_type: str = "bilocalization") -> dict:
    expected = int(ctx.expected_output or 0)
    count = sum(1 for i in ctx.output.issues if i.get("type") == issue_type)
    return {"exact_type_count": count == expected, "type_count_got": count}


@evaluator
def no_issue_description_contains(ctx: EvalContext) -> dict:
    kw = normalize(ctx.expected_output or "")
    failing = [i.get("description", "") for i in ctx.output.issues
               if kw in normalize(i.get("description", ""))]
    result: dict = {"no_desc_match": not failing}
    if failing:
        result["offending_desc"] = failing[0][:80]
    return result


@evaluator
def profile_not_contains_keyword(ctx: EvalContext) -> dict:
    if not ctx.expected_output:
        return {}
    keywords = [k.strip().lower() for k in ctx.expected_output.split(",") if k.strip()]
    bg = (ctx.output.background or "").lower()
    found = [k for k in keywords if k in bg]
    result: dict = {"profile_not_contains": not found}
    if found:
        result["found_keywords"] = ", ".join(found)
    return result


@evaluator
def min_chunk_count(ctx: EvalContext) -> dict:
    expected = int(ctx.expected_output or 1)
    count = ctx.output.fragment_count
    return {"chunks_ok": count >= expected, "chunks_got": count}


@evaluator
def group_ids_present(ctx: EvalContext) -> dict:
    if not ctx.expected_output:
        return {}
    expected = {s.strip() for s in ctx.expected_output.split(",")}
    found = set(ctx.output.group_ids)
    present = expected & found
    missing = expected - found
    score = len(present) / len(expected) if expected else 1.0
    result: dict = {"group_id_recall": score}
    if missing:
        result["missing_group_ids"] = ", ".join(sorted(missing))
    return result


@evaluator
def group_absent(ctx: EvalContext) -> dict:
    target = (ctx.expected_output or "").strip()
    found = target in ctx.output.group_ids
    return {"group_absent_pass": not found}


@evaluator
def relation_text_not_contains_keyword(ctx: EvalContext) -> dict:
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
    result: dict = {"no_copresence": not found}
    if found:
        result["offending_relations"] = "; ".join(found[:3])
    return result


@evaluator
def max_relation_count(ctx: EvalContext) -> dict:
    max_count = int(ctx.expected_output or 1)
    count = ctx.output.fragment_count
    return {"dedup_ok": count <= max_count, "relation_count_got": count}


@evaluator
def all_locations_contain_keyword(ctx: EvalContext) -> dict:
    kw = (ctx.expected_output or "").strip().lower()
    names = ctx.output.location_names
    all_match = all(kw in n.lower() for n in names) if names else False
    failing = [n for n in names if kw not in n.lower()]
    result: dict = {"all_locations_match": all_match}
    if failing:
        result["locations_not_matching"] = ", ".join(failing)
    return result


@evaluator
def entity_check_has_issue_type(ctx: EvalContext) -> dict:
    kw = (ctx.expected_output or "").strip()
    found = any(kw in i.get("type", "") for i in ctx.output.issues)
    return {"entity_check_type_found": found}


@evaluator
def entity_check_no_issue_about_entity(ctx: EvalContext) -> dict:
    kw = normalize(ctx.expected_output or "")
    offending = [
        i for i in ctx.output.issues
        if kw in normalize(i.get("entity_id") or "")
        or kw in normalize(i.get("description") or "")
    ]
    result: dict = {"no_entity_match": not offending}
    if offending:
        result["offending_entity"] = offending[0].get("description", "")[:80]
    return result


@evaluator
def entity_check_no_issues(ctx: EvalContext) -> dict:
    count = len(ctx.output.issues)
    return {"no_issues": count == 0, "issue_count": count}
