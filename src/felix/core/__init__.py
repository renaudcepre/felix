"""Noyau générique schemaless de Felix — entités/propriétés/relations libres.

Promu depuis l'expérience evals/generic (15/17, checks 6/6) : un seul code,
plusieurs domaines, discipline de schéma émergent via describe_schema, et un
check de cohérence « voisinage + judge » sans aucune sémantique de domaine codée.

Surface publique du noyau (le bot B et les evals importent d'ici).
"""
from __future__ import annotations

from felix.core.agent import SYSTEM_PROMPT, create_core_agent
from felix.core.check import CheckVerdict, consistency_check
from felix.core.deps import GenericDeps
from felix.core.graph import (
    NARRATIVE_REL,
    all_entities,
    all_relations,
    merge_entity_into,
    recent_entities,
    rel_label,
    rename_or_merge,
    render_recent_block,
)
from felix.core.models import RelationRef, ToolCard
from felix.core.profile import CHANTIER_PROFILE, SCENARIO_PROFILE, EntityType, Profile
from felix.core.user_edits import (
    consume_unnotified_edits,
    recent_user_edits,
    record_user_edit,
    render_user_edits_block,
)

__all__ = [
    "CHANTIER_PROFILE",
    "NARRATIVE_REL",
    "SCENARIO_PROFILE",
    "SYSTEM_PROMPT",
    "CheckVerdict",
    "EntityType",
    "GenericDeps",
    "Profile",
    "RelationRef",
    "ToolCard",
    "all_entities",
    "all_relations",
    "consistency_check",
    "consume_unnotified_edits",
    "create_core_agent",
    "merge_entity_into",
    "recent_entities",
    "recent_user_edits",
    "record_user_edit",
    "rel_label",
    "rename_or_merge",
    "render_recent_block",
    "render_user_edits_block",
]
