"""Dépendances racine du noyau générique, partagées par tous les tools.

GenericDeps est la classe racine (inversion de dépendance : le bot B la ré-exporte
sous le nom AtelierDeps). Elle porte le driver, les cartes UI, le journal des
écritures, l'ensemble des entités touchées ce tour, et le profil de domaine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from felix.core.models import ToolCard
    from felix.core.profile import Profile


@dataclass
class GenericDeps:
    driver: AsyncDriver
    # Cartes structurées poussées par les tools pendant le run,
    # drainées par la route SSE (et lues telles quelles par les evals).
    ui_events: list[ToolCard] = field(default_factory=list)
    # Journal des écritures (ancienne → nouvelle valeur) : le check de
    # cohérence doit voir le DELTA, pas seulement l'état final — une écriture
    # qui écrase une valeur contradictoire rend l'état final auto-cohérent
    # (finding : l'alibi écrasé avant le check).
    write_log: list[str] = field(default_factory=list)
    # Entités créées/modifiées ce tour — la route lance un consistency_check
    # sur chacune après la boucle agent.
    touched_ids: set[str] = field(default_factory=set)
    # Profil de domaine optionnel : oriente describe_schema, le prompt et le check.
    profile: Profile | None = None
