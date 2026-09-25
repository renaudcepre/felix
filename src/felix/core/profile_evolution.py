"""Évolution PURE du profil — Étape 4 du plan `maintenance_profile.md`.

Un changement de schéma VALIDÉ (``core/schema_changes.py``) migre le PASSÉ (le
graphe) ; ``evolve_profile`` migre le FUTUR (le profil déclaratif qui orientera
la PROCHAINE ingestion). Les deux effets d'un même clic « accepter », dans deux
fonctions pures séparées — aucun appel réseau ici, aucun appel LLM.

``PromoteVerbs`` ajoute — ou étend — un ``RelationSpec`` structurel : le domaine/
portée vient de ``report.observed_pairs`` (les couples de types réellement reliés
par les arêtes promues), la glose et les exemples des verbes verbatim d'origine
(``report.verbes``). ``MergeTypes`` renomme le(s) type(s) source(s) en la cible,
partout où ils apparaissent (``entity_types`` ET ``relation_vocabulary``).
"""
from __future__ import annotations

import dataclasses

from felix.core.profile import EntityType, Profile, RelationSpec
from felix.core.schema_changes import (
    ChangeReport,
    MergeTypes,
    PromoteVerbs,
    SchemaChange,
)


def _merge_examples(existing: str, new_verbes: list[str]) -> str:
    """Concatène les exemples existants (glose FR séparée par virgule) et les
    nouveaux verbes, dédupliqués en ordre stable."""
    seen = [e.strip() for e in existing.split(",") if e.strip()]
    for verbe in new_verbes:
        if verbe not in seen:
            seen.append(verbe)
    return ", ".join(seen)


def _evolve_promote_verbs(
    profile: Profile, change: PromoteVerbs, report: ChangeReport
) -> Profile:
    subjects = tuple(sorted({s for s, _ in report.observed_pairs}))
    objects = tuple(sorted({o for _, o in report.observed_pairs}))
    existing = next(
        (s for s in profile.relation_vocabulary if s.name == change.rel_type), None
    )

    if existing is None:
        gloss = report.verbes[0] if report.verbes else change.rel_type.lower()
        new_spec = RelationSpec(
            name=change.rel_type, gloss=gloss, subjects=subjects, objects=objects,
            examples=", ".join(report.verbes),
        )
        new_vocab = (*profile.relation_vocabulary, new_spec)
    else:
        # Extension : union des sujets/objets observés, verbes ajoutés aux
        # exemples — la glose d'origine reste (elle ne doit pas changer de
        # sens à chaque nouvelle fiche qui reconfirme le même type).
        merged_subjects = tuple(sorted(set(existing.subjects) | set(subjects)))
        merged_objects = tuple(sorted(set(existing.objects) | set(objects)))
        new_spec = RelationSpec(
            name=change.rel_type, gloss=existing.gloss,
            subjects=merged_subjects, objects=merged_objects,
            allow_self=existing.allow_self,
            examples=_merge_examples(existing.examples, report.verbes),
        )
        new_vocab = tuple(
            new_spec if s.name == change.rel_type else s for s in profile.relation_vocabulary
        )
    return dataclasses.replace(profile, relation_vocabulary=new_vocab)


def _rename_type(entity_type: str, change: MergeTypes) -> str:
    return change.target if entity_type in change.sources else entity_type


def _evolve_merge_types(
    profile: Profile, change: MergeTypes, report: ChangeReport
) -> Profile:
    merged_types: dict[str, EntityType] = {}
    for et in profile.entity_types:
        name = _rename_type(et.name, change)
        if name not in merged_types:
            merged_types[name] = EntityType(name=name, keys=et.keys, note=et.note)
        else:
            existing = merged_types[name]
            merged_keys = tuple(dict.fromkeys((*existing.keys, *et.keys)))
            merged_types[name] = EntityType(
                name=name, keys=merged_keys, note=existing.note or et.note,
            )
    new_entity_types = tuple(merged_types.values())

    new_vocab = tuple(
        RelationSpec(
            name=spec.name, gloss=spec.gloss,
            subjects=tuple(dict.fromkeys(_rename_type(s, change) for s in spec.subjects)),
            objects=tuple(dict.fromkeys(_rename_type(o, change) for o in spec.objects)),
            allow_self=spec.allow_self, examples=spec.examples,
        )
        for spec in profile.relation_vocabulary
    )
    return dataclasses.replace(
        profile, entity_types=new_entity_types, relation_vocabulary=new_vocab
    )


def evolve_profile(profile: Profile, change: SchemaChange, report: ChangeReport) -> Profile:
    """Le profil qui résulte de l'application d'un changement VALIDÉ — pure,
    aucun accès réseau. ``report`` est celui du run RÉEL (``preview=False``) :
    ``observed_pairs``/``verbes`` y décrivent ce qui a vraiment été converti."""
    if isinstance(change, PromoteVerbs):
        return _evolve_promote_verbs(profile, change, report)
    return _evolve_merge_types(profile, change, report)
