from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from felix.ingest.utils import normalize

logger = logging.getLogger(__name__)

THRESHOLD_AUTO = 0.85
THRESHOLD_FUZZY = 0.60
MIN_SHARED_WORD_LEN = 3


@dataclass
class ResolvedEntity:
    id: str
    name: str
    is_new: bool = False
    score: float | None = None


@dataclass
class AmbiguousMatch:
    best_id: str
    best_name: str
    score: float
    candidates: list[tuple[str, str, float]] = field(default_factory=list)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize(name)).strip("-")


def _has_different_first_name(norm_a: str, norm_b: str) -> bool:
    """Return True if both names have 2+ words and share a surname but differ on first name."""
    parts_a = norm_a.split()
    parts_b = norm_b.split()
    if len(parts_a) < 2 or len(parts_b) < 2:  # noqa: PLR2004
        return False
    # Same last word (surname) but different first word
    return parts_a[-1] == parts_b[-1] and parts_a[0] != parts_b[0]


def _shares_significant_word(norm_a: str, norm_b: str) -> bool:
    """Return True if the two names share at least one exact word of MIN_SHARED_WORD_LEN+ chars."""
    words_a = {w for w in norm_a.split() if len(w) >= MIN_SHARED_WORD_LEN}
    words_b = {w for w in norm_b.split() if len(w) >= MIN_SHARED_WORD_LEN}
    return bool(words_a & words_b)


def _coverage_score(norm_query: str, norm_candidate: str) -> float:
    """WRatio with a length penalty when the query has fewer tokens than the candidate.

    token_set_ratio (used internally by WRatio) inflates scores when the query is a
    strict subset of a longer name ("Voss" vs "Lena Voss" → 100%).  Applying
    sqrt(n_query / n_candidate) brings that down to ~0.71, landing in AmbiguousMatch
    territory instead of auto-resolving.
    """
    raw = fuzz.WRatio(norm_query, norm_candidate) / 100.0
    n_q = len(norm_query.split())
    n_c = len(norm_candidate.split())
    return raw * (n_q / n_c) ** 0.5 if n_q < n_c else raw


def _collect_candidates(
    norm: str,
    existing: dict[str, str],
    aliases: dict[str, list[str]],
) -> list[tuple[str, str, float]]:
    candidates: list[tuple[str, str, float]] = []
    for eid, ename in existing.items():
        norm_existing = normalize(ename)
        if _has_different_first_name(norm, norm_existing):
            continue
        score = _coverage_score(norm, norm_existing)
        if score >= THRESHOLD_AUTO or (
            score >= THRESHOLD_FUZZY and _shares_significant_word(norm, norm_existing)
        ):
            candidates.append((eid, ename, score))
        for alias in aliases.get(eid, []):
            norm_alias = normalize(alias)
            if _has_different_first_name(norm, norm_alias):
                continue
            alias_score = _coverage_score(norm, norm_alias)
            if alias_score > score and (
                alias_score >= THRESHOLD_AUTO
                or (alias_score >= THRESHOLD_FUZZY and _shares_significant_word(norm, norm_alias))
            ):
                candidates.append((eid, ename, alias_score))
    return candidates


def fuzzy_match_entity(
    name: str,
    existing: dict[str, str],
    aliases: dict[str, list[str]] | None = None,
) -> ResolvedEntity | AmbiguousMatch:
    aliases = aliases or {}
    norm = normalize(name)

    # Exact match on normalized name
    for eid, ename in existing.items():
        if normalize(ename) == norm:
            return ResolvedEntity(id=eid, name=ename)

    # Exact match on alias
    for eid, alias_list in aliases.items():
        for alias in alias_list:
            if normalize(alias) == norm:
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
        logger.debug("fuzzy auto: %r → %r (score=%.2f)", name, best_name, best_score)
        return ResolvedEntity(id=best_id, name=best_name, score=best_score)

    # Ambiguous
    logger.debug(
        "fuzzy ambiguous: %r → %r (score=%.2f, candidates=%s)",
        name,
        best_name,
        best_score,
        [(n, round(s, 2)) for _, n, s in candidates],
    )
    return AmbiguousMatch(
        best_id=best_id,
        best_name=best_name,
        score=best_score,
        candidates=candidates,
    )
