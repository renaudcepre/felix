"""Evaluators for scene analysis quality."""
from __future__ import annotations

from dataclasses import dataclass

from protest.evals import EvalContext, evaluator

from evals._utils import normalize

_EPHEMERAL_PHYSICAL_TERMS = [
    "red eyes", "tired", "fatigue", "hand on", "holds", "holding",
    "driving since", "sitting", "standing", "stands up",
    "sweating", "bleeding", "wounded", "injured",
]


@dataclass
class CharExtractionResult:
    char_extraction: float
    all_found: bool
    missing_chars: str = ""


@evaluator
def extracts_expected_characters(ctx: EvalContext) -> CharExtractionResult:
    if not ctx.expected_output:
        return CharExtractionResult(char_extraction=1.0, all_found=True)
    expected_names = [normalize(n.strip()) for n in ctx.expected_output.split(",") if n.strip()]
    extracted_names = [normalize(c.name) for c in ctx.output.characters]
    found, missing = 0, []
    for exp in expected_names:
        if any(exp in ext or ext in exp for ext in extracted_names):
            found += 1
        else:
            missing.append(exp)
    score = found / len(expected_names) if expected_names else 1.0
    return CharExtractionResult(
        char_extraction=score,
        all_found=not missing,
        missing_chars=", ".join(missing) if missing else "",
    )


@dataclass
class RoleResult:
    role_accuracy: float
    wrong_roles: str = ""
    missing_characters: str = ""


@evaluator
def character_role_accuracy(ctx: EvalContext) -> RoleResult:
    if not ctx.expected_output:
        return RoleResult(role_accuracy=1.0)
    expected = {}
    for raw_pair in ctx.expected_output.split(","):
        pair = raw_pair.strip()
        if ":" not in pair:
            continue
        name, role = pair.rsplit(":", 1)
        expected[normalize(name.strip())] = role.strip().lower()
    extracted = {normalize(c.name): normalize(c.role) for c in ctx.output.characters}
    correct, wrong, missing = 0, [], []
    for exp_name, exp_role in expected.items():
        matched = False
        for ext_name, ext_role in extracted.items():
            if exp_name in ext_name or ext_name in exp_name:
                matched = True
                if exp_role in ext_role or ext_role in exp_role:
                    correct += 1
                else:
                    wrong.append(f"{exp_name}: expected={exp_role}, got={ext_role}")
                break
        if not matched:
            missing.append(exp_name)
    total = len(expected)
    return RoleResult(
        role_accuracy=correct / total if total else 1.0,
        wrong_roles="; ".join(wrong) if wrong else "",
        missing_characters="; ".join(missing) if missing else "",
    )


@evaluator
def era_accuracy(ctx: EvalContext) -> bool:
    if not ctx.expected_output:
        return True
    return ctx.expected_output.strip().lower() == ctx.output.era.strip().lower()


@evaluator
def location_accuracy(ctx: EvalContext) -> bool:
    if not ctx.expected_output:
        return True
    expected_kw = normalize(ctx.expected_output.strip())
    got = normalize(ctx.output.location.name)
    return expected_kw in got or got in expected_kw


@evaluator
def no_character_present(ctx: EvalContext) -> bool:
    if not ctx.expected_output:
        return True
    target = ctx.expected_output.strip().lower()
    return not any(target in name or name in target for name in [c.name.lower() for c in ctx.output.characters])


@dataclass
class DescriptionResult:
    description_contains: bool
    matched_keyword: str = ""
    description_got: str = ""


@evaluator
def character_description_contains(ctx: EvalContext, character: str = "") -> DescriptionResult:
    if not ctx.expected_output:
        return DescriptionResult(description_contains=True)
    target_name = normalize(character)
    matched_char = next(
        (c for c in ctx.output.characters
         if target_name in normalize(c.name) or normalize(c.name) in target_name),
        None,
    )
    if matched_char is None:
        return DescriptionResult(description_contains=False, description_got=f"{character} not found")
    desc = normalize(matched_char.description or "")
    keywords = [normalize(k.strip()) for k in ctx.expected_output.split(",") if k.strip()]
    found = next((k for k in keywords if k in desc), None)
    return DescriptionResult(
        description_contains=found is not None,
        matched_keyword=found or "none",
        description_got=matched_char.description or "(none)",
    )


@dataclass
class EphemeralResult:
    no_ephemeral_physical: bool
    flagged_terms: str = ""
    description_got: str = ""


@evaluator
def no_ephemeral_physical_description(ctx: EvalContext, character: str = "") -> EphemeralResult:
    target_name = normalize(character)
    matched_char = next(
        (c for c in ctx.output.characters
         if target_name in normalize(c.name) or normalize(c.name) in target_name),
        None,
    )
    if matched_char is None:
        return EphemeralResult(no_ephemeral_physical=False, description_got=f"{character} not found")
    desc = normalize(matched_char.description or "")
    flagged = [t for t in _EPHEMERAL_PHYSICAL_TERMS if t in desc]
    return EphemeralResult(
        no_ephemeral_physical=not flagged,
        flagged_terms=", ".join(flagged) if flagged else "none",
        description_got=matched_char.description or "(none)",
    )
