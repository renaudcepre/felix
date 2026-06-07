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
from felix.core.graph import all_entities, all_relations
from felix.core.models import ToolCard
from felix.core.profile import SCENARIO_PROFILE, EntityType, Profile

__all__ = [
    "SCENARIO_PROFILE",
    "SYSTEM_PROMPT",
    "CheckVerdict",
    "EntityType",
    "GenericDeps",
    "Profile",
    "ToolCard",
    "all_entities",
    "all_relations",
    "consistency_check",
    "create_core_agent",
]
