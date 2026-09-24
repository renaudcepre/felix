"""Persistance du profil ÉVOLUÉ par projet — Étape 3 du plan `maintenance_profile.md`.

Le schéma émerge des documents ingérés (détecteur + validation humaine, cf.
`core/schema_detector.py` et `core/profile_evolution.py`) : chaque changement
validé fait évoluer le ``Profile`` PUR en mémoire, qui doit ensuite survivre
entre deux requêtes. Un méta-nœud ``:ProjectProfile`` (PAS ``:GenEntity`` — ce
n'est pas une entité du domaine, c'est la CONFIGURATION du projet) porte le
profil sérialisé en JSON, versionné à chaque sauvegarde.

Deux fonctions pures de (dé)sérialisation (``profile_to_dict``/``profile_from_dict``,
round-trip exact, tuples reconstruits) + deux fonctions Neo4j (``load``/``save``).
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from felix.core.profile import EntityType, Profile, RelationSpec

if TYPE_CHECKING:
    from neo4j import AsyncDriver


def profile_to_dict(profile: Profile) -> dict:
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
    }


def profile_from_dict(data: dict) -> Profile:
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


async def save_project_profile(driver: AsyncDriver, profile: Profile, *, project: str) -> int:
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
            project=project, data=data,
        )
        record = await result.single()
    return record["version"]
