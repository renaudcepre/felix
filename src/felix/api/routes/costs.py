"""Route du coût persistant par projet (#coût) — total agrégé (tokens + USD)
et compte d'opérations par nature (`chat`/`ingest`), depuis les nœuds
`:CostEntry` posés à chaque tour de chat / import de document (cf.
`felix.core.costs`). Consommée par la topbar du front (total du projet,
rafraîchi après chaque tour/import) — INDÉPENDANT de l'historique des
messages, survit à « nouvelle conversation »/archivage.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from felix.api.deps import Neo4jDriver  # noqa: TC001 — FastAPI résout au runtime (DI)
from felix.core.costs import project_cost_totals
from felix.core.projects import DEFAULT_PROJECT

router = APIRouter(prefix="/api/costs", tags=["costs"])


class ProjectCostOut(BaseModel):
    request_tokens: int
    response_tokens: int
    total_tokens: int
    cost_usd: float | None
    count_by_kind: dict[str, int]


@router.get("")
async def get_project_costs(
    driver: Neo4jDriver, project: str = DEFAULT_PROJECT
) -> ProjectCostOut:
    totals = await project_cost_totals(driver, project=project)
    return ProjectCostOut(**totals)
