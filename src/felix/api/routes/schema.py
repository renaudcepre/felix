"""Route du schéma ÉMERGENT (Étape 7, `plans/maintenance_profile.md`) — la file
de validation humaine : voir le profil courant d'un projet, lister les
propositions déterministes du détecteur, appliquer un changement VALIDÉ (migre
le passé ET fait évoluer le profil stocké).

Le seul choix évolutif aujourd'hui est ``emergent`` (cf. ``felix.atelier.agent``) —
ces routes s'y rattachent explicitement plutôt que de généraliser à un profil
arbitraire : pas de première abstraction avant un second cas concret.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from felix.api.deps import Neo4jDriver  # noqa: TC001 — FastAPI résout au runtime (DI)
from felix.atelier.agent import ATELIER_CHOICES, resolve_profile
from felix.core.profile_evolution import evolve_profile
from felix.core.profile_store import profile_to_dict, save_project_profile
from felix.core.projects import DEFAULT_PROJECT
from felix.core.schema_changes import ChangeReport, SchemaChange, apply_schema_change
from felix.core.schema_detector import Proposal, detect_proposals

router = APIRouter(prefix="/api/schema", tags=["schema"])

_CHOICE_KEY = "emergent"


class ApplyChangeRequest(BaseModel):
    project: str = DEFAULT_PROJECT
    change: SchemaChange


class ApplyChangeResponse(BaseModel):
    report: ChangeReport
    profile: dict
    version: int


@router.get("/profile")
async def get_profile(driver: Neo4jDriver, project: str = DEFAULT_PROJECT) -> dict:
    """Le profil RÉEL de ce projet — stocké s'il existe, sinon le seed
    (cf. ``resolve_profile`` : aucun changement n'a encore été validé)."""
    choice = ATELIER_CHOICES[_CHOICE_KEY]
    profile = await resolve_profile(driver, choice, project=project)
    return profile_to_dict(profile)


@router.get("/proposals")
async def get_proposals(
    driver: Neo4jDriver, project: str = DEFAULT_PROJECT, profile: str = _CHOICE_KEY,
) -> list[Proposal]:
    """Propositions déterministes (aucun appel LLM) pour ce projet — chacune
    porte son rapport en PREVIEW, exactement ce que ferait le clic « accepter »."""
    choice = ATELIER_CHOICES.get(profile, ATELIER_CHOICES[_CHOICE_KEY])
    resolved = await resolve_profile(driver, choice, project=project)
    return await detect_proposals(driver, project=project, profile=resolved)


@router.post("/apply")
async def post_apply_change(driver: Neo4jDriver, body: ApplyChangeRequest) -> ApplyChangeResponse:
    """Applique un changement VALIDÉ par l'humain : migre le passé (le graphe),
    fait évoluer le profil (en partant du seed si rien n'est encore stocké) et
    sauvegarde la nouvelle version. Retourne le rapport ET le nouveau profil —
    la file de validation affiche les deux."""
    choice = ATELIER_CHOICES[_CHOICE_KEY]
    report = await apply_schema_change(driver, body.change, project=body.project, preview=False)
    current = await resolve_profile(driver, choice, project=body.project)
    new_profile = evolve_profile(current, body.change, report)
    version = await save_project_profile(driver, new_profile, project=body.project)
    return ApplyChangeResponse(
        report=report, profile=profile_to_dict(new_profile), version=version
    )
