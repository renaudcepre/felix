"""Evaluators for scene analysis quality."""
from __future__ import annotations

from protest.evals import EvalContext, evaluator

from evals._utils import normalize

# Terms indicating ephemeral physical state (not a permanent characteristic).
_EPHEMERAL_PHYSICAL_TERMS = [
    "red eyes", "tired", "fatigue", "hand on", "holds", "holding",
    "driving since", "sitting", "standing", "stands up",
    "sweating", "bleeding", "wounded", "injured",
]


@evaluator
def character_role_accuracy(ctx: EvalContext) -> dict:
    if not ctx.expected_output or not isinstance(ctx.expected_output, str):
        return {}
    expected = {}
    for raw_pair in ctx.expected_output.split(","):
        pair = raw_pair.strip()
        if ":" not in pair:
            continue
        name, role = pair.rsplit(":", 1)
        expected[normalize(name.strip())] = role.strip().lower()
    extracted = {normalize(c.name): normalize(c.role) for c in ctx.output.characters}
    correct, wrong_roles, missing = 0, [], []
    for exp_name, exp_role in expected.items():
        matched = False
        for ext_name, ext_role in extracted.items():
            if exp_name in ext_name or ext_name in exp_name:
                matched = True
                if exp_role in ext_role or ext_role in exp_role:
                    correct += 1
                else:
                    wrong_roles.append(f"{exp_name}: expected={exp_role}, got={ext_role}")
                break
        if not matched:
            missing.append(exp_name)
    total = len(expected)
    result: dict = {"role_accuracy": correct / total if total else 1.0}
    if wrong_roles:
        result["wrong_roles"] = "; ".join(wrong_roles)
    if missing:
        result["missing_characters"] = "; ".join(missing)
    return result


@evaluator
def extracts_expected_characters(ctx: EvalContext) -> dict:
    if not ctx.expected_output or not isinstance(ctx.expected_output, str):
        return {}
    expected_names = [normalize(n.strip()) for n in ctx.expected_output.split(",") if n.strip()]
    extracted_names = [normalize(c.name) for c in ctx.output.characters]
    found, missing = 0, []
    for exp in expected_names:
        if any(exp in ext or ext in exp for ext in extracted_names):
            found += 1
        else:
            missing.append(exp)
    score = found / len(expected_names) if expected_names else 1.0
    result: dict = {"char_extraction": score}
    if missing:
        result["missing_chars"] = ", ".join(missing)
    return result


@evaluator
def era_accuracy(ctx: EvalContext) -> dict:
    if not ctx.expected_output or not isinstance(ctx.expected_output, str):
        return {}
    expected_era = ctx.expected_output.strip().lower()
    got_era = ctx.output.era.strip().lower()
    return {"era_match": expected_era == got_era, "era_got": got_era}


@evaluator
def location_accuracy(ctx: EvalContext) -> dict:
    if not ctx.expected_output or not isinstance(ctx.expected_output, str):
        return {}
    expected_kw = normalize(ctx.expected_output.strip())
    got = normalize(ctx.output.location.name)
    return {
        "location_match": expected_kw in got or got in expected_kw,
        "location_got": ctx.output.location.name,
    }


@evaluator
def no_character_present(ctx: EvalContext) -> dict:
    if not ctx.expected_output or not isinstance(ctx.expected_output, str):
        return {}
    target = ctx.expected_output.strip().lower()
    extracted = [c.name.lower() for c in ctx.output.characters]
    found = any(target in name or name in target for name in extracted)
    return {"absent_pass": not found}


@evaluator
def character_description_contains(ctx: EvalContext, character: str = "") -> dict:
    if not ctx.expected_output or not isinstance(ctx.expected_output, str):
        return {}
    target_name = normalize(character)
    matched = next(
        (c for c in ctx.output.characters
         if target_name in normalize(c.name) or normalize(c.name) in target_name),
        None,
    )
    if matched is None:
        return {"description_contains": False, "reason": f"{character} not found"}
    desc = normalize(matched.description or "")
    keywords = [normalize(k.strip()) for k in ctx.expected_output.split(",") if k.strip()]
    found = next((k for k in keywords if k in desc), None)
    return {
        "description_contains": found is not None,
        "matched_keyword": found or "none",
        "description_got": matched.description or "(none)",
    }


@evaluator
def character_type_correct(ctx: EvalContext, character: str = "") -> dict:
    if not ctx.expected_output or not isinstance(ctx.expected_output, str):
        return {}
    target_name = normalize(character)
    expected_type = ctx.expected_output.strip().lower()
    matched = next(
        (c for c in ctx.output.characters
         if target_name in normalize(c.name) or normalize(c.name) in target_name),
        None,
    )
    if matched is None:
        return {"type_correct": False, "reason": f"{character} not found"}
    return {"type_correct": matched.character_type == expected_type, "type_got": matched.character_type}


@evaluator
def no_ephemeral_physical_description(ctx: EvalContext, character: str = "") -> dict:
    target_name = normalize(character)
    matched = next(
        (c for c in ctx.output.characters
         if target_name in normalize(c.name) or normalize(c.name) in target_name),
        None,
    )
    if matched is None:
        return {"no_ephemeral_physical": False, "reason": f"{character} not found"}
    desc = normalize(matched.description or "")
    flagged = [t for t in _EPHEMERAL_PHYSICAL_TERMS if t in desc]
    return {
        "no_ephemeral_physical": not flagged,
        "flagged_terms": ", ".join(flagged) if flagged else "none",
        "description_got": matched.description or "(none)",
    }
