from __future__ import annotations

from dataclasses import dataclass

from evals.expected import (
    EXPECTED_CHARACTER_IDS,
    EXPECTED_IRINA_BACKGROUND_KEYWORDS,
    EXPECTED_IRINA_BACKGROUND_KEYWORDS_MIN_MATCH,
    EXPECTED_IRINA_FRAGMENT_COUNT,
    EXPECTED_MIN_ISSUES,
    EXPECTED_MIN_RELATIONS,
    EXPECTED_SCENE_COUNT,
    IRINA_ID,
)


@dataclass
class EvalResult:
    name: str
    passed: bool
    score: float  # 0.0–1.0
    details: str = ""


def eval_scenes_stored(export: dict) -> EvalResult:
    n = len(export.get("scenes", []))
    passed = n == EXPECTED_SCENE_COUNT
    return EvalResult(
        name="scenes_stored",
        passed=passed,
        score=min(n / EXPECTED_SCENE_COUNT, 1.0),
        details=f"{n}/{EXPECTED_SCENE_COUNT} scenes stockees",
    )


def eval_characters_found(export: dict) -> EvalResult:
    stored_ids = {c["id"] for c in export.get("characters", [])}
    found = EXPECTED_CHARACTER_IDS & stored_ids
    score = len(found) / len(EXPECTED_CHARACTER_IDS)
    missing = EXPECTED_CHARACTER_IDS - stored_ids
    details = f"{len(found)}/{len(EXPECTED_CHARACTER_IDS)} trouves"
    if missing:
        details += f" | manquants: {', '.join(sorted(missing))}"
    return EvalResult(
        name="characters_found",
        passed=score == 1.0,
        score=score,
        details=details,
    )


def eval_irina_fragments(export: dict) -> EvalResult:
    frags = [
        f for f in export.get("character_fragments", [])
        if f.get("character_id") == IRINA_ID
    ]
    n = len(frags)
    passed = n >= EXPECTED_IRINA_FRAGMENT_COUNT
    return EvalResult(
        name="irina_fragments",
        passed=passed,
        score=min(n / EXPECTED_IRINA_FRAGMENT_COUNT, 1.0),
        details=f"{n}/{EXPECTED_IRINA_FRAGMENT_COUNT} fragments pour {IRINA_ID}",
    )


def eval_timeline_populated(export: dict) -> EvalResult:
    events = export.get("timeline_events", [])
    scenes = export.get("scenes", [])
    if not scenes:
        return EvalResult("timeline_populated", False, 0.0, "aucune scene")
    scene_ids = {s["id"] for s in scenes}
    event_scene_ids = {e.get("scene_id") for e in events if e.get("scene_id")}
    covered = scene_ids & event_scene_ids
    score = len(covered) / len(scene_ids)
    with_date = sum(
        1 for e in events
        if e.get("date") and e["date"] != "unknown" and not e["date"].endswith("-01-01")
    )
    details = f"{len(covered)}/{len(scene_ids)} scenes avec event | {with_date} dates precises"
    return EvalResult(
        name="timeline_populated",
        passed=score == 1.0,
        score=score,
        details=details,
    )


def eval_issue_detected(export: dict) -> EvalResult:
    issues = export.get("issues", [])
    checker_issues = [
        i for i in issues
        if i.get("type") in ("character_contradiction", "missing_info", "timeline_inconsistency")
    ]
    n = len(checker_issues)
    passed = n >= EXPECTED_MIN_ISSUES
    all_types = [i.get("type") for i in issues]
    return EvalResult(
        name="issue_detected",
        passed=passed,
        score=1.0 if passed else 0.0,
        details=f"{n} issue(s) checker | tous types: {all_types}",
    )


def eval_profile_grounded(export: dict) -> EvalResult:
    chars = export.get("characters", [])
    irina = next((c for c in chars if c.get("id") == IRINA_ID), None)
    if not irina:
        return EvalResult("profile_grounded", False, 0.0, "Irina non trouvee")
    background = (irina.get("background") or "").lower()
    matches = [kw for kw in EXPECTED_IRINA_BACKGROUND_KEYWORDS if kw in background]
    n = len(matches)
    passed = n >= EXPECTED_IRINA_BACKGROUND_KEYWORDS_MIN_MATCH
    score = n / len(EXPECTED_IRINA_BACKGROUND_KEYWORDS)
    return EvalResult(
        name="profile_grounded",
        passed=passed,
        score=score,
        details=f"{n}/{len(EXPECTED_IRINA_BACKGROUND_KEYWORDS)} keywords: {matches} | bg: {background[:80]}",
    )


def eval_relations_present(export: dict) -> EvalResult:
    rels = export.get("character_relations", [])
    n = len(rels)
    passed = n >= EXPECTED_MIN_RELATIONS
    return EvalResult(
        name="relations_present",
        passed=passed,
        score=1.0 if passed else 0.0,
        details=f"{n} relation(s) stockee(s)",
    )


def run_all(export: dict) -> list[EvalResult]:
    return [
        eval_scenes_stored(export),
        eval_characters_found(export),
        eval_irina_fragments(export),
        eval_timeline_populated(export),
        eval_issue_detected(export),
        eval_profile_grounded(export),
        eval_relations_present(export),
    ]


def print_report(results: list[EvalResult]) -> None:
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n{'='*60}")
    print(f"EVAL REPORT  {passed}/{total} passed")
    print(f"{'='*60}")
    for r in results:
        status = "OK" if r.passed else "KO"
        bar = "#" * int(r.score * 10) + "." * (10 - int(r.score * 10))
        print(f"  {status} [{bar}] {r.name:<25} {r.details}")
    print(f"{'='*60}\n")
