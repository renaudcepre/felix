from __future__ import annotations

from fastapi import APIRouter

from felix.api.deps import Neo4jDriver
from felix.api.models import Issue
from felix.graph.consistency import run_all_checks

router = APIRouter(prefix="/api/checks", tags=["checks"])


@router.post("/run")
async def run_checks(driver: Neo4jDriver) -> list[Issue]:
    issues = await run_all_checks(driver)
    return [Issue(**i) for i in issues]
