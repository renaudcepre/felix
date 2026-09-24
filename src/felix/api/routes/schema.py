"""Route du schéma ÉMERGENT (Étape 7, `plans/maintenance_profile.md`) — la file
de validation humaine : voir le profil courant d'un projet, lister les
propositions déterministes du détecteur, appliquer un changement VALIDÉ (migre
le passé ET fait évoluer le profil stocké).

Le seul choix évolutif aujourd'hui est ``emergent`` (cf. ``felix.atelier.agent``) —
ces routes s'y rattachent explicitement plutôt que de généraliser à un profil
arbitraire : pas de première abstraction avant un second cas concret.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from pydantic import BaseModel

from felix.api.deps import Neo4jDriver  # noqa: TC001 — FastAPI résout au runtime (DI)
from felix.atelier.agent import ATELIER_CHOICES, resolve_profile
from felix.core.profile_evolution import evolve_profile
from felix.core.profile_store import (
    load_project_profile_version,
    load_rejected_changes,
    profile_to_dict,
    save_project_profile,
    save_rejected_change,
)
from felix.core.projects import DEFAULT_PROJECT
from felix.core.schema_changes import ChangeReport, SchemaChange, apply_schema_change
from felix.core.schema_detector import Proposal, detect_proposals

if TYPE_CHECKING:
    from felix.core.profile import Profile

router = APIRouter(prefix="/api/schema", tags=["schema"])

_CHOICE_KEY = "emergent"


def _require_profile(profile: Profile | None) -> Profile:
    """`resolve_profile` reste `Profile | None` pour couvrir tout choix (cf.
    `felix.atelier.agent.AgentChoice`, un choix non évolutif peut ne porter aucun
    profil) ; ces routes ne s'appliquent qu'au choix ÉMERGENT (cf. docstring du
    module), qui en a toujours un — None ici signalerait un appel hors de ce
    contrat plutôt qu'un crash plus loin dans detect_proposals/evolve_profile."""
    if profile is None:
        raise ValueError(f"aucun profil résolu pour le choix « {_CHOICE_KEY} »")
    return profile


class ApplyChangeRequest(BaseModel):
    project: str = DEFAULT_PROJECT
    change: SchemaChange


class ApplyChangeResponse(BaseModel):
    report: ChangeReport
    profile: dict
    version: int


class RejectChangeRequest(BaseModel):
    project: str = DEFAULT_PROJECT
    change: SchemaChange


@router.get("/profile")
async def get_profile(driver: Neo4jDriver, project: str = DEFAULT_PROJECT) -> dict:
    """Le profil RÉEL de ce projet — stocké s'il existe, sinon le seed
    (cf. ``resolve_profile`` : aucun changement n'a encore été validé), avec sa
    `version` (0 tant que rien n'a été validé) — la vue en lecture seule du
    front l'affiche à côté des types de relation appris."""
    choice = ATELIER_CHOICES[_CHOICE_KEY]
    profile = _require_profile(await resolve_profile(driver, choice, project=project))
    version = await load_project_profile_version(driver, project=project)
    return {**profile_to_dict(profile), "version": version}


@router.get("/proposals")
async def get_proposals(
    driver: Neo4jDriver, project: str = DEFAULT_PROJECT, profile: str = _CHOICE_KEY,
) -> list[Proposal]:
    """Propositions déterministes (aucun appel LLM) pour ce projet — chacune
    porte son rapport en PREVIEW, exactement ce que ferait le clic « accepter »."""
    choice = ATELIER_CHOICES.get(profile, ATELIER_CHOICES[_CHOICE_KEY])
    resolved = _require_profile(await resolve_profile(driver, choice, project=project))
    return await detect_proposals(driver, project=project, profile=resolved)


@router.post("/apply")
async def post_apply_change(driver: Neo4jDriver, body: ApplyChangeRequest) -> ApplyChangeResponse:
    """Applique un changement VALIDÉ par l'humain : migre le passé (le graphe),
    fait évoluer le profil (en partant du seed si rien n'est encore stocké) et
    sauvegarde la nouvelle version. Retourne le rapport ET le nouveau profil —
    la file de validation affiche les deux."""
    choice = ATELIER_CHOICES[_CHOICE_KEY]
    report = await apply_schema_change(driver, body.change, project=body.project, preview=False)
    current = _require_profile(await resolve_profile(driver, choice, project=body.project))
    new_profile = evolve_profile(current, body.change, report)
    version = await save_project_profile(driver, new_profile, project=body.project)
    return ApplyChangeResponse(
        report=report, profile=profile_to_dict(new_profile), version=version
    )


@router.post("/reject")
async def post_reject_change(driver: Neo4jDriver, body: RejectChangeRequest) -> list[dict]:
    """Refuse UNE proposition : persistée (``profile_store.save_rejected_change``)
    pour que ``detect_proposals`` ne la re-propose plus (même ensemble source —
    verbe_slugs ou sources — quel que soit le nom cible tenté ensuite). Rend la
    liste des refus à jour, pour un affichage sans second aller-retour."""
    await save_rejected_change(driver, body.change, project=body.project)
    return await load_rejected_changes(driver, project=body.project)
