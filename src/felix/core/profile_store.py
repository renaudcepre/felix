"""Persistance du profil ÉVOLUÉ par projet — Étape 3 du plan `maintenance_profile.md`.

Le schéma émerge des documents ingérés (détecteur + validation humaine, cf.
`core/schema_detector.py` et `core/profile_evolution.py`) : chaque changement
validé fait évoluer le ``Profile`` PUR en mémoire, qui doit ensuite survivre
entre deux requêtes. Un méta-nœud ``:ProjectProfile`` (PAS ``:GenEntity`` — ce
n'est pas une entité du domaine, c'est la CONFIGURATION du projet) porte le
profil sérialisé en JSON, versionné à chaque sauvegarde.

Deux fonctions pures de (dé)sérialisation (``profile_to_dict``/``profile_from_dict``,
round-trip exact, tuples reconstruits) + deux fonctions Neo4j (``load``/``save``).

Étape 8 (file de validation) : les changements REFUSÉS par l'humain vivent dans
``p.rejected``, un champ SIBLING de ``p.data`` sur le MÊME nœud — jamais dans le
``Profile`` lui-même (il n'a pas à savoir ce qu'on a refusé, seulement ce qui a
été validé) — round-trip de ``profile_to_dict``/``profile_from_dict`` intact.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from felix.core.profile import (
    EMERGENT_SEED_PROFILE,
    EntityType,
    Profile,
    RelationSpec,
)

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from felix.core.schema_changes import SchemaChange


def profile_to_dict(profile: Profile) -> dict[str, Any]:
    """Sérialise un ``Profile`` en dict JSON-compatible (tuples → listes)."""
    return {
        "name": profile.name,
        "description": profile.description,
        "entity_types": [
            {"name": et.name, "keys": list(et.keys), "note": et.note}
            for et in profile.entity_types
        ],
        "modeling_rules": list(profile.modeling_rules),
        "consistency_rules": list(profile.consistency_rules),
        "relation_vocabulary": [
            {
                "name": spec.name,
                "gloss": spec.gloss,
                "subjects": list(spec.subjects),
                "objects": list(spec.objects),
                "allow_self": spec.allow_self,
                "examples": spec.examples,
            }
            for spec in profile.relation_vocabulary
        ],
        "narrative_rel": profile.narrative_rel,
        "manages_events": profile.manages_events,
        "code_only_relations": list(profile.code_only_relations),
        "narrative_link_hint": profile.narrative_link_hint,
        "narrative_verb_example": profile.narrative_verb_example,
        "non_contradiction_examples": list(profile.non_contradiction_examples),
    }


def profile_from_dict(data: dict[str, Any]) -> Profile:
    """Reconstruit un ``Profile`` depuis un dict (ex. ``json.loads`` de la base) —
    inverse exact de ``profile_to_dict`` : les listes redeviennent des tuples."""
    return Profile(
        name=data["name"],
        description=data["description"],
        entity_types=tuple(
            EntityType(name=et["name"], keys=tuple(et["keys"]), note=et.get("note", ""))
            for et in data.get("entity_types", [])
        ),
        modeling_rules=tuple(data.get("modeling_rules", [])),
        consistency_rules=tuple(data.get("consistency_rules", [])),
        relation_vocabulary=tuple(
            RelationSpec(
                name=spec["name"],
                gloss=spec["gloss"],
                subjects=tuple(spec.get("subjects", [])),
                objects=tuple(spec.get("objects", [])),
                allow_self=spec.get("allow_self", False),
                examples=spec.get("examples", ""),
            )
            for spec in data.get("relation_vocabulary", [])
        ),
        narrative_rel=data.get("narrative_rel", ""),
        manages_events=data.get("manages_events", False),
        code_only_relations=tuple(data.get("code_only_relations", [])),
        # Profils stockés AVANT ces champs (2026-09-25) : seul un choix évolutif
        # (l'émergent) est stocké, donc une clé absente reprend la valeur de SON
        # seed — sinon un projet existant perdrait ses non-contradictions.
        narrative_link_hint=data.get(
            "narrative_link_hint", EMERGENT_SEED_PROFILE.narrative_link_hint
        ),
        narrative_verb_example=data.get(
            "narrative_verb_example", EMERGENT_SEED_PROFILE.narrative_verb_example
        ),
        non_contradiction_examples=tuple(
            data.get(
                "non_contradiction_examples",
                EMERGENT_SEED_PROFILE.non_contradiction_examples,
            )
        ),
    )


async def load_project_profile(driver: AsyncDriver, *, project: str) -> Profile | None:
    """Le profil stocké du projet, ou ``None`` si aucun n'a encore été sauvegardé
    (avant la première validation de changement — l'appelant se rabat alors sur
    le profil de départ du choix, cf. ``felix.atelier.agent.resolve_profile``)."""
    async with driver.session() as session:
        result = await session.run(
            "MATCH (p:ProjectProfile {project: $project}) RETURN p.data AS data",
            project=project,
        )
        record = await result.single()
    if record is None or record["data"] is None:
        return None
    return profile_from_dict(json.loads(record["data"]))


async def save_project_profile(
    driver: AsyncDriver, profile: Profile, *, project: str
) -> int:
    """Sauvegarde le profil ÉVOLUÉ du projet, version incrémentée. Rend la
    nouvelle version (1 à la première sauvegarde)."""
    data = json.dumps(profile_to_dict(profile))
    async with driver.session() as session:
        result = await session.run(
            """
            MERGE (p:ProjectProfile {project: $project})
            ON CREATE SET p.version = 0
            SET p.data = $data, p.version = p.version + 1
            RETURN p.version AS version
            """,
            project=project,
            data=data,
        )
        record = await result.single()
    assert record is not None  # MERGE ... RETURN garantit toujours une ligne
    version: int = record["version"]
    return version


async def load_project_profile_version(driver: AsyncDriver, *, project: str) -> int:
    """Version courante du profil stocké (0 si rien n'a encore été sauvegardé —
    cohérent avec ``ON CREATE SET p.version = 0`` de ``save_project_profile``).
    Sert la lecture seule ``GET /api/schema/profile`` (le seed n'a pas de
    version tant qu'aucun changement n'a été validé)."""
    async with driver.session() as session:
        result = await session.run(
            "MATCH (p:ProjectProfile {project: $project}) RETURN p.version AS version",
            project=project,
        )
        record = await result.single()
    if record is None or record["version"] is None:
        return 0
    version: int = record["version"]
    return version


async def load_rejected_changes(
    driver: AsyncDriver, *, project: str
) -> list[dict[str, Any]]:
    """Changements REFUSÉS par l'humain pour ce projet, en dicts (mêmes clés
    qu'un ``SchemaChange.model_dump()``) — ``schema_detector.detect_proposals``
    s'en sert pour ne plus re-proposer un cluster déjà tranché."""
    async with driver.session() as session:
        result = await session.run(
            "MATCH (p:ProjectProfile {project: $project}) RETURN p.rejected AS rejected",
            project=project,
        )
        record = await result.single()
    if record is None or record["rejected"] is None:
        return []
    return [json.loads(s) for s in record["rejected"]]


async def save_rejected_change(
    driver: AsyncDriver, change: SchemaChange, *, project: str
) -> None:
    """Ajoute UN changement refusé à la liste persistée (append, jamais de
    remplacement — un refus n'efface pas les précédents). ``MERGE`` : refuser
    une proposition avant toute validation ne doit PAS créer de profil stocké
    (``p.data`` reste absent, cf. tests de non-régression du round-trip)."""
    payload = json.dumps(change.model_dump())
    async with driver.session() as session:
        await session.run(
            """
            MERGE (p:ProjectProfile {project: $project})
            ON CREATE SET p.version = 0
            SET p.rejected = coalesce(p.rejected, []) + $payload
            """,
            project=project,
            payload=payload,
        )
