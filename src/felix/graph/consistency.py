"""Post-import graph-based consistency checks."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from rapidfuzz import fuzz

from felix.graph.repositories.characters import (
    get_character_fragments,
    list_all_character_relations,
    list_all_characters,
)

if TYPE_CHECKING:
    from neo4j import AsyncDriver


async def check_duplicate_characters(driver: AsyncDriver) -> list[dict]:
    """Find characters with suspiciously similar names (fuzzy match > 70)."""
    characters = await list_all_characters(driver)
    issues: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for i, a in enumerate(characters):
        for b in characters[i + 1 :]:
            pair = (min(a["id"], b["id"]), max(a["id"], b["id"]))
            if pair in seen:
                continue
            seen.add(pair)
            score = fuzz.token_set_ratio(a["name"].lower(), b["name"].lower())
            if score > 70:  # noqa: PLR2004
                issues.append({
                    "id": f"dup-{a['id']}-{b['id']}",
                    "type": "duplicate_suspect",
                    "severity": "warning",
                    "scene_id": None,
                    "entity_id": a["id"],
                    "description": (
                        f"'{a['name']}' and '{b['name']}' have similar names "
                        f"(score: {score}). They may be the same character."
                    ),
                })
    return issues


_CONTRADICTION_PAIRS = [
    ({"blonde", "blond", "fair-haired", "fair"}, {"dark", "black", "brunette", "dark-haired"}),
    ({"tall"}, {"short", "small", "petite"}),
    ({"young"}, {"old", "elderly", "aged"}),
    ({"thin", "slim", "lean"}, {"heavy", "stocky", "broad", "large"}),
]


async def check_physical_contradictions(driver: AsyncDriver) -> list[dict]:
    """Find characters with contradictory physical descriptions across fragments."""
    characters = await list_all_characters(driver)
    issues: list[dict] = []

    for char in characters:
        fragments = await get_character_fragments(driver, char["id"])
        descriptions = [
            (f["scene_id"], f["description"].lower())
            for f in fragments
            if f.get("description")
        ]
        if len(descriptions) < 2:  # noqa: PLR2004
            continue

        for left_kws, right_kws in _CONTRADICTION_PAIRS:
            left_scenes = [
                sid for sid, desc in descriptions if any(kw in desc for kw in left_kws)
            ]
            right_scenes = [
                sid for sid, desc in descriptions if any(kw in desc for kw in right_kws)
            ]
            if left_scenes and right_scenes:
                matched_left = next(kw for kw in left_kws if any(kw in d for _, d in descriptions))
                matched_right = next(kw for kw in right_kws if any(kw in d for _, d in descriptions))
                issues.append({
                    "id": str(uuid.uuid4()),
                    "type": "physical_contradiction",
                    "severity": "warning",
                    "scene_id": left_scenes[0],
                    "entity_id": char["id"],
                    "description": (
                        f"{char['name']} is described as '{matched_left}' in {left_scenes[0]} "
                        f"but '{matched_right}' in {right_scenes[0]}."
                    ),
                })
    return issues


async def check_contradictory_relations(driver: AsyncDriver) -> list[dict]:
    """Find characters with contradictory relation types (e.g. ally + enemy)."""
    contradictions = [
        ({"ally", "allied", "friend"}, {"enemy", "rival", "adversary", "foe"}),
        ({"mentor", "teacher"}, {"student", "apprentice"}),
    ]

    relations = await list_all_character_relations(driver)
    issues: list[dict] = []
    pair_rels: dict[tuple[str, str], list[str]] = {}

    for rel in relations:
        pair = (min(rel["character_id_a"], rel["character_id_b"]),
                max(rel["character_id_a"], rel["character_id_b"]))
        pair_rels.setdefault(pair, []).append(rel["relation_type"].lower())

    for (a, b), types in pair_rels.items():
        for left_kws, right_kws in contradictions:
            has_left = any(any(kw in t for kw in left_kws) for t in types)
            has_right = any(any(kw in t for kw in right_kws) for t in types)
            if has_left and has_right:
                issues.append({
                    "id": str(uuid.uuid4()),
                    "type": "contradictory_relations",
                    "severity": "warning",
                    "scene_id": None,
                    "entity_id": a,
                    "description": (
                        f"Characters '{a}' and '{b}' have contradictory relations: "
                        f"{', '.join(types)}."
                    ),
                })
    return issues


async def run_all_checks(driver: AsyncDriver) -> list[dict]:
    """Run all graph-based consistency checks and return combined issues."""
    issues: list[dict] = []
    issues.extend(await check_duplicate_characters(driver))
    issues.extend(await check_physical_contradictions(driver))
    issues.extend(await check_contradictory_relations(driver))
    return issues
