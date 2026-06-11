"""Dépendances racine du noyau générique, partagées par tous les tools.

GenericDeps est la classe racine (inversion de dépendance : le bot B la ré-exporte
sous le nom AtelierDeps). Elle porte le driver, les cartes UI, le journal des
écritures, l'ensemble des entités touchées ce tour, et le profil de domaine.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from felix.core.projects import DEFAULT_PROJECT

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from felix.core.models import ToolCard
    from felix.core.profile import Profile


@dataclass
class GenericDeps:
    driver: AsyncDriver
    # Projet/histoire courant (#60) : le « tenant » de toutes les lectures et
    # écritures du tour. Posé par la route d'après la sélection du front, jamais
    # par le LLM. Défaut = projet de repli (evals, appels sans sélection).
    project_id: str = DEFAULT_PROJECT
    # Cartes structurées poussées par les tools pendant le run,
    # drainées par la route SSE (et lues telles quelles par les evals).
    ui_events: list[ToolCard] = field(default_factory=list)
    # Journal des écritures (ancienne → nouvelle valeur) : le check de
    # cohérence doit voir le DELTA, pas seulement l'état final — une écriture
    # qui écrase une valeur contradictoire rend l'état final auto-cohérent
    # (finding : l'alibi écrasé avant le check).
    write_log: list[str] = field(default_factory=list)
    # Entités créées/modifiées ce tour (toutes confondues).
    touched_ids: set[str] = field(default_factory=set)
    # Sous-ensemble de `touched_ids` où une contradiction est POSSIBLE ce tour :
    # entité ayant reçu une RELATION, une participation à un ÉVÉNEMENT, ou un
    # ÉCRASEMENT de valeur. C'est là que vivent les checks prouvés (temporel
    # « mort puis agit », spatial, valeur divergente écrasée). La route ne lance
    # le juge QUE sur ce sous-ensemble — pas sur chaque création/prop additive ni
    # sur les nœuds événement (jamais sujets) : sinon ~20-30 appels/tour et de longs
    # blancs en fin de tour sous rate-limit. Voir route `_consistency_alerts`.
    check_candidates: set[str] = field(default_factory=set)
    # Profil de domaine optionnel : oriente describe_schema, le prompt et le check.
    profile: Profile | None = None
    # Routage du tour : posé par la ROUTE d'après le gate stateless (RouteDecision,
    # cf. felix.atelier.agent.build_gate_agent) quand le message apporte du contenu.
    # La route ne dispatche les extracteurs (entités/relieur/chroniqueur) + le juge
    # QUE si ce flag est vrai — un bavardage/une question ne déclenche AUCUNE
    # écriture (hallu impossible par construction, et tour conversationnel moins cher).
    extraction_requested: bool = False
    # Sérialise l'allocation d'`ordre` d'add_event : un même run peut émettre
    # plusieurs add_event dans une seule réponse → pydantic-ai les exécute en
    # parallèle, et un max(ordre)+1 concurrent collisionnerait sur le même id.
    event_seq_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, repr=False, compare=False
    )
