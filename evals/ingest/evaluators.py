"""Evaluators for scene analysis quality."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals._utils import normalize
from felix.ingest.models import SceneAnalysis


@dataclass
class CharacterRoleAccuracy(Evaluator[str, SceneAnalysis]):
    """Check that characters are extracted with correct roles.

    expected_output format: "Name:role,Name:role,..."
    Example: "Jakes Milton:participant,Elias:mentioned"
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, SceneAnalysis]
    ) -> dict[str, float | str]:
        if not ctx.expected_output or not isinstance(ctx.expected_output, str):
            return {}

        expected = {}
        for raw_pair in ctx.expected_output.split(","):
            pair = raw_pair.strip()
            if ":" not in pair:
                continue
            name, role = pair.rsplit(":", 1)
            expected[normalize(name.strip())] = role.strip().lower()

        output = ctx.output
        extracted = {}
        for char in output.characters:
            extracted[normalize(char.name)] = normalize(char.role)

        correct = 0
        total = len(expected)
        wrong_roles: list[str] = []
        missing: list[str] = []

        for exp_name, exp_role in expected.items():
            # Find best match in extracted
            matched = False
            for ext_name, ext_role in extracted.items():
                if exp_name in ext_name or ext_name in exp_name:
                    matched = True
                    if exp_role in ext_role or ext_role in exp_role:
                        correct += 1
                    else:
                        wrong_roles.append(
                            f"{exp_name}: expected={exp_role}, got={ext_role}"
                        )
                    break
            if not matched:
                missing.append(exp_name)

        score = correct / total if total else 1.0

        result: dict[str, float | str] = {
            "role_accuracy": score,
        }
        if wrong_roles:
            result["wrong_roles"] = "; ".join(wrong_roles)
        if missing:
            result["missing_characters"] = "; ".join(missing)
        return result


@dataclass
class ExtractsExpectedCharacters(Evaluator[str, SceneAnalysis]):
    """Check that all expected character names are found (regardless of role).

    expected_output: comma-separated character names.
    """

    def evaluate(
        self, ctx: EvaluatorContext[str, SceneAnalysis]
    ) -> dict[str, float | str]:
        if not ctx.expected_output or not isinstance(ctx.expected_output, str):
            return {}

        expected_names = [
            normalize(n.strip())
            for n in ctx.expected_output.split(",")
            if n.strip()
        ]
        extracted_names = [normalize(c.name) for c in ctx.output.characters]

        found = 0
        missing = []
        for exp in expected_names:
            if any(exp in ext or ext in exp for ext in extracted_names):
                found += 1
            else:
                missing.append(exp)

        score = found / len(expected_names) if expected_names else 1.0
        result: dict[str, float | str] = {"char_extraction": score}
        if missing:
            result["missing_chars"] = ", ".join(missing)
        return result


@dataclass
class EraAccuracy(Evaluator[str, SceneAnalysis]):
    """Check that the extracted era matches expected."""

    def evaluate(
        self, ctx: EvaluatorContext[str, SceneAnalysis]
    ) -> dict[str, bool | str]:
        if not ctx.expected_output or not isinstance(ctx.expected_output, str):
            return {}
        expected_era = ctx.expected_output.strip().lower()
        got_era = ctx.output.era.strip().lower()
        return {
            "era_match": expected_era == got_era,
            "era_got": got_era,
        }


@dataclass
class LocationAccuracy(Evaluator[str, SceneAnalysis]):
    """Check that the extracted location name contains expected keywords."""

    def evaluate(
        self, ctx: EvaluatorContext[str, SceneAnalysis]
    ) -> dict[str, bool | str]:
        if not ctx.expected_output or not isinstance(ctx.expected_output, str):
            return {}
        expected_kw = normalize(ctx.expected_output.strip())
        got = normalize(ctx.output.location.name)
        return {
            "location_match": expected_kw in got or got in expected_kw,
            "location_got": ctx.output.location.name,
        }


@dataclass
class NoCharacterPresent(Evaluator[str, SceneAnalysis]):
    """Check that a character is NOT extracted (negative test)."""

    def evaluate(
        self, ctx: EvaluatorContext[str, SceneAnalysis]
    ) -> dict[str, bool]:
        if not ctx.expected_output or not isinstance(ctx.expected_output, str):
            return {}
        target = ctx.expected_output.strip().lower()
        extracted = [c.name.lower() for c in ctx.output.characters]
        found = any(target in name or name in target for name in extracted)
        return {"absent_pass": not found}


# Terms indicating ephemeral physical state (not a permanent characteristic).
_EPHEMERAL_PHYSICAL_TERMS = [
    "red eyes",
    "tired",
    "fatigue",
    "hand on",
    "holds",
    "holding",
    "driving since",
    "sitting",
    "standing",
    "stands up",
    "sweating",
    "bleeding",
    "wounded",
    "injured",
]


@dataclass
class CharacterDescriptionContains(Evaluator[str, SceneAnalysis]):
    """Check that a specific character's description contains an expected keyword.

    character: name of the character to check.
    expected_output: keyword that must appear in the description.
    """

    character: str = ""

    def evaluate(
        self, ctx: EvaluatorContext[str, SceneAnalysis]
    ) -> dict[str, bool | str]:
        if not ctx.expected_output or not isinstance(ctx.expected_output, str):
            return {}
        target_name = normalize(self.character)
        keyword = normalize(ctx.expected_output.strip())
        matched = next(
            (
                c
                for c in ctx.output.characters
                if target_name in normalize(c.name) or normalize(c.name) in target_name
            ),
            None,
        )
        if matched is None:
            return {"description_contains": False, "reason": f"{self.character} not found"}
        desc = normalize(matched.description or "")
        keywords = [normalize(k.strip()) for k in ctx.expected_output.split(",") if k.strip()]
        found = next((k for k in keywords if k in desc), None)
        return {
            "description_contains": found is not None,
            "matched_keyword": found or "none",
            "description_got": matched.description or "(none)",
        }


@dataclass
class CharacterTypeCorrect(Evaluator[str, SceneAnalysis]):
    """Check that a specific character has the expected character_type.

    character: name of the character to check.
    expected_output: "individual" or "group".
    """

    character: str = ""

    def evaluate(
        self, ctx: EvaluatorContext[str, SceneAnalysis]
    ) -> dict[str, bool | str]:
        if not ctx.expected_output or not isinstance(ctx.expected_output, str):
            return {}
        target_name = normalize(self.character)
        expected_type = ctx.expected_output.strip().lower()
        matched = next(
            (
                c
                for c in ctx.output.characters
                if target_name in normalize(c.name) or normalize(c.name) in target_name
            ),
            None,
        )
        if matched is None:
            return {"type_correct": False, "reason": f"{self.character} not found"}
        got_type = matched.character_type
        return {
            "type_correct": got_type == expected_type,
            "type_got": got_type,
        }


@dataclass
class NoEphemeralPhysicalDescription(Evaluator[str, SceneAnalysis]):
    """Check that a character's description contains no ephemeral physical state.

    A physical description must describe permanent traits (height, build, scars…),
    not momentary states (tired, red eyes, hand on the wheel…).

    character: name of the character to check.
    """

    character: str = ""

    def evaluate(
        self, ctx: EvaluatorContext[str, SceneAnalysis]
    ) -> dict[str, bool | str]:
        target_name = normalize(self.character)
        matched = next(
            (
                c
                for c in ctx.output.characters
                if target_name in normalize(c.name) or normalize(c.name) in target_name
            ),
            None,
        )
        if matched is None:
            return {"no_ephemeral_physical": False, "reason": f"{self.character} not found"}

        desc = normalize(matched.description or "")
        flagged = [t for t in _EPHEMERAL_PHYSICAL_TERMS if t in desc]
        return {
            "no_ephemeral_physical": not flagged,
            "flagged_terms": ", ".join(flagged) if flagged else "none",
            "description_got": matched.description or "(none)",
        }
