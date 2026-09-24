"""Détecteur DÉTERMINISTE de propositions de changement de schéma — Étape 5 du
plan `maintenance_profile.md`. AUCUN appel LLM : les LIE_A (verbe verbatim, #68)
sont le CAPTEUR — un verbe qui revient est un type structurel candidat.

Deux familles de propositions, une par sens de dérive constaté sur le terrain :
(a) clusters de verbes narratifs (LIE_A) qui reviennent → ``PromoteVerbs`` ;
(b) types d'entité quasi-doublons (même singulier, ou ressemblance floue) →
``MergeTypes`` du plus rare vers le plus fréquent.

Chaque ``Proposal`` porte son ``ChangeReport`` en PREVIEW (``apply_schema_change``
avec ``preview=True``) : la file de validation (hors scope ici) montre à
l'humain exactement ce que ferait le clic « accepter », avant qu'il ne clique.
"""
from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from pydantic import BaseModel
from rapidfuzz import fuzz

from felix.core.graph import NARRATIVE_REL
from felix.core.profile_store import load_rejected_changes
from felix.core.schema_changes import (
    ChangeReport,
    MergeTypes,
    PromoteVerbs,
    SchemaChange,
    apply_schema_change,
)

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from felix.core.profile import Profile

# Mots de fonction FRANÇAIS en tête d'un verbe LIE_A (« est réglé par », « qui
# pilote ») — retirés avant de prendre le premier token substantiel. Volontairement
# petit et plat (frozenset module-level) : c'est une heuristique de CLUSTERING,
# pas une lemmatisation — elle n'a besoin d'être ni exhaustive ni linguistiquement
# savante, seulement stable et déterministe.
_STOPWORDS = frozenset({
    "est", "sont", "a", "ont", "se", "s", "ne", "n", "pour", "permet",
    "permettent", "de", "d", "l", "la", "le", "les", "en", "y", "qui", "il",
    "elle", "on",
})

def _normalize(text: str) -> str:
    """Minuscules, sans accents, ponctuation → espaces (cf. felix.ingest.document)."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    bare = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9']+", " ", bare).strip()


def verb_head(verbe: str) -> str:
    """Tête normalisée d'un verbe narratif — la clé de clustering. « règle »,
    « qui règle », « est réglé par » retombent tous sur « regle ». Vide si le
    verbe ne contient QUE des mots de fonction (rien de substantiel)."""
    for token in _normalize(verbe).split():
        cleaned = token.strip("'")
        if cleaned and cleaned not in _STOPWORDS:
            return cleaned[:-1] if cleaned.endswith("s") and len(cleaned) > 1 else cleaned
    return ""


def cluster_verbs(edges: list[dict], *, min_count: int) -> dict[str, list[dict]]:
    """Groupe des arêtes LIE_A (dicts avec au moins la clé ``verbe``) par tête de
    verbe — pure, testable sans Neo4j. Ne garde que les clusters atteignant
    ``min_count`` arêtes ; un verbe sans tête substantielle (pur mot de
    fonction) n'entre dans aucun cluster."""
    clusters: dict[str, list[dict]] = {}
    for edge in edges:
        head = verb_head(str(edge.get("verbe", "")))
        if not head:
            continue
        clusters.setdefault(head, []).append(edge)
    return {head: rows for head, rows in clusters.items() if len(rows) >= min_count}


def _singular(entity_type: str) -> str:
    norm = _normalize(entity_type).replace(" ", "")
    return norm[:-1] if norm.endswith("s") and len(norm) > 1 else norm


_FUZZY_TYPE_THRESHOLD = 85


def pair_near_duplicate_types(counts: dict[str, int]) -> list[MergeTypes]:
    """Types d'entité quasi-doublons (même singulier normalisé, ou ressemblance
    floue ≥ 85) → ``MergeTypes(sources=[le plus rare], target=le plus fréquent)``.
    Pure, testable sans Neo4j. ``counts`` = {entity_type: nombre d'entités}."""
    types = sorted(counts)
    merges: list[MergeTypes] = []
    already_merged: set[str] = set()
    for i, type_a in enumerate(types):
        if type_a in already_merged:
            continue
        for type_b in types[i + 1:]:
            if type_b in already_merged:
                continue
            same_singular = _singular(type_a) == _singular(type_b)
            fuzzy = fuzz.ratio(_normalize(type_a), _normalize(type_b)) >= _FUZZY_TYPE_THRESHOLD
            if not (same_singular or fuzzy):
                continue
            rarer, target = (
                (type_a, type_b) if counts[type_a] <= counts[type_b] else (type_b, type_a)
            )
            merges.append(MergeTypes(sources=[rarer], target=target))
            already_merged.add(rarer)
    return merges


def _rejection_signature(change: dict) -> tuple[str, frozenset[str]]:
    """Signature stable d'un changement, pour comparer une proposition à un refus
    passé — INDÉPENDANTE du nom cible choisi (``rel_type``/``target``) : ce qui
    définit « le même refus », c'est l'ensemble SOURCE (les verbes ou les types
    qu'on a écartés), pas le nom qu'on leur proposait. Fonctionne aussi bien sur
    un ``SchemaChange.model_dump()`` que sur un dict rechargé depuis la base."""
    if change.get("kind") == "promote_verbs":
        return ("promote_verbs", frozenset(change.get("verbe_slugs", [])))
    return ("merge_types", frozenset(change.get("sources", [])))


class Proposal(BaseModel):
    """Une proposition de changement de schéma, avec son rapport en PREVIEW —
    ce que montrerait la file de validation avant le clic « accepter »."""

    change: SchemaChange
    report: ChangeReport


async def _fetch_narrative_edges(driver: AsyncDriver, *, project: str) -> list[dict]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (:GenEntity {project: $project})
                  -[r:REL {rel_type: $narr}]->
                  (:GenEntity {project: $project})
            RETURN r.verbe AS verbe, r.verbe_slug AS verbe_slug
            ORDER BY r.verbe_slug
            """,
            project=project, narr=NARRATIVE_REL,
        )
        return [dict(r) for r in await result.data()]


async def _fetch_entity_type_counts(driver: AsyncDriver, *, project: str) -> dict[str, int]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (e:GenEntity {project: $project})
            WHERE NOT e.entity_type IN ['document', 'evenement']
            RETURN e.entity_type AS entity_type, count(e) AS n
            """,
            project=project,
        )
        rows = [dict(r) for r in await result.data()]
    return {row["entity_type"]: row["n"] for row in rows}


async def _verb_proposals(
    driver: AsyncDriver, *, project: str, min_count: int
) -> list[Proposal]:
    edges = await _fetch_narrative_edges(driver, project=project)
    clusters = cluster_verbs(edges, min_count=min_count)

    proposals: list[Proposal] = []
    for head in sorted(clusters):
        rows = clusters[head]
        rel_type = head.upper()
        slugs = sorted({row["verbe_slug"] for row in rows})
        change = PromoteVerbs(verbe_slugs=slugs, rel_type=rel_type)
        try:
            report = await apply_schema_change(driver, change, project=project, preview=True)
        except ValueError:
            # rel_type dérivé invalide (machinerie, vide…) — pas une proposition
            # exploitable ; on ne réimplémente pas ici la garde de schema_changes.
            continue
        proposals.append(Proposal(change=change, report=report))
    return proposals


async def _type_proposals(driver: AsyncDriver, *, project: str) -> list[Proposal]:
    counts = await _fetch_entity_type_counts(driver, project=project)
    merges = pair_near_duplicate_types(counts)

    proposals: list[Proposal] = []
    for change in merges:
        try:
            report = await apply_schema_change(driver, change, project=project, preview=True)
        except ValueError:
            continue
        proposals.append(Proposal(change=change, report=report))
    return proposals


async def detect_proposals(
    driver: AsyncDriver, *, project: str, profile: Profile, min_count: int = 2
) -> list[Proposal]:
    """Propositions DÉTERMINISTES pour ce projet, aucun appel LLM :
    (a) clusters de verbes LIE_A promouvables (≥ ``min_count`` arêtes) ;
    (b) quasi-doublons de type d'entité fusionnables ;
    en excluant (Étape 8) celles dont la SOURCE (verbe_slugs / sources) a déjà
    été refusée par l'humain (cf. ``profile_store.load_rejected_changes``) — un
    verbe déjà entièrement promu n'a de toute façon plus d'arête LIE_A à
    proposer (cf. ci-dessus), mais un refus doit rester valable même si le
    cluster REVIENT identique à un run ultérieur.

    ``profile`` n'est pas encore consulté ici (les clusters partent des arêtes
    LIE_A VIVANTES) ; il est gardé dans la signature pour un filtrage futur."""
    rejected = await load_rejected_changes(driver, project=project)
    rejected_sigs = {_rejection_signature(r) for r in rejected}

    verb_proposals = await _verb_proposals(driver, project=project, min_count=min_count)
    type_proposals = await _type_proposals(driver, project=project)
    all_proposals = verb_proposals + type_proposals
    return [
        p for p in all_proposals
        if _rejection_signature(p.change.model_dump()) not in rejected_sigs
    ]
