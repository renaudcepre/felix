from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

THRESHOLD_AUTO = 0.85
THRESHOLD_FUZZY = 0.70


@dataclass
class ResolvedEntity:
    id: str
    name: str
    is_new: bool = False


@dataclass
class AmbiguousMatch:
    best_id: str
    best_name: str
    score: float
    candidates: list[tuple[str, str, float]] = field(default_factory=list)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _normalize(name)).strip("-")


def _normalize(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _has_different_first_name(norm_a: str, norm_b: str) -> bool:
    """Return True if both names have 2+ words and share a surname but differ on first name."""
    parts_a = norm_a.split()
    parts_b = norm_b.split()
    if len(parts_a) < 2 or len(parts_b) < 2:
        return False
    # Same last word (surname) but different first word
    return parts_a[-1] == parts_b[-1] and parts_a[0] != parts_b[0]


def _collect_candidates(
    norm: str,
    existing: dict[str, str],
    aliases: dict[str, list[str]],
) -> list[tuple[str, str, float]]:
    candidates: list[tuple[str, str, float]] = []
    for eid, ename in existing.items():
        norm_existing = _normalize(ename)
        if _has_different_first_name(norm, norm_existing):
            continue
        score = SequenceMatcher(None, norm, norm_existing).ratio()
        if score >= THRESHOLD_FUZZY:
            candidates.append((eid, ename, score))
        for alias in aliases.get(eid, []):
            norm_alias = _normalize(alias)
            if _has_different_first_name(norm, norm_alias):
                continue
            alias_score = SequenceMatcher(None, norm, norm_alias).ratio()
            if alias_score >= THRESHOLD_FUZZY and alias_score > score:
                candidates.append((eid, ename, alias_score))
    return candidates


def fuzzy_match_entity(
    name: str,
    existing: dict[str, str],
    aliases: dict[str, list[str]] | None = None,
) -> ResolvedEntity | AmbiguousMatch:
    aliases = aliases or {}
    norm = _normalize(name)

    # Exact match on normalized name
    for eid, ename in existing.items():
        if _normalize(ename) == norm:
            return ResolvedEntity(id=eid, name=ename)

    # Exact match on alias
    for eid, alias_list in aliases.items():
        for alias in alias_list:
            if _normalize(alias) == norm:
                return ResolvedEntity(id=eid, name=existing[eid])

    # Fuzzy matching
    candidates = _collect_candidates(norm, existing, aliases)

    # Deduplicate by entity id, keep best score
    best_per_entity: dict[str, tuple[str, str, float]] = {}
    for eid, ename, score in candidates:
        if eid not in best_per_entity or score > best_per_entity[eid][2]:
            best_per_entity[eid] = (eid, ename, score)
    candidates = sorted(best_per_entity.values(), key=lambda x: x[2], reverse=True)

    if not candidates:
        new_id = slugify(name)
        return ResolvedEntity(id=new_id, name=name, is_new=True)

    best_id, best_name, best_score = candidates[0]

    if best_score >= THRESHOLD_AUTO:
        return ResolvedEntity(id=best_id, name=best_name)

    # Ambiguous
    return AmbiguousMatch(
        best_id=best_id,
        best_name=best_name,
        score=best_score,
        candidates=candidates,
    )
