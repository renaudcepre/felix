"""Routes du registre de projets/histoires (#60).

Créer/lister seulement (v1) : « Nouvelle histoire » au front = POST ici puis
switch local. La suppression attend l'export par histoire (#42) — on ne jette
pas une bible sans pouvoir l'archiver.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from felix.api.deps import (
    Neo4jDriver,  # noqa: TC001 — FastAPI résout l'annotation au runtime (DI)
)
from felix.api.models import ProjectCreate, ProjectOut
from felix.core import create_project, list_projects

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
async def get_projects(driver: Neo4jDriver) -> list[ProjectOut]:
    """Tous les projets du registre, plus récents d'abord."""
    return [ProjectOut(**p) for p in await list_projects(driver)]


@router.post("")
async def post_project(body: ProjectCreate, driver: Neo4jDriver) -> ProjectOut:
    """Crée (ou retrouve — MERGE sur le slug du nom) un projet."""
    project = await create_project(driver, body.name)
    if project is None:
        raise HTTPException(status_code=422, detail=f"Nom invalide : {body.name!r}")
    return ProjectOut(**project)
