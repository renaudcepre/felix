"""Pipeline eval task with protest fixture-based setup."""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from protest import Use, console, fixture

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from evals.pipeline.task import FIXTURES_ROOT, PipelineQueryResult, _query, _run_pipeline


@fixture()
async def unified_pipeline() -> AsyncDriver:
    """Run the unified pipeline import once, shared across all cases."""
    console.print("[dim]pipeline:[/] starting import...")
    driver = await _run_pipeline(FIXTURES_ROOT / "unified")
    console.print("[green]pipeline:[/] import done")
    return driver


async def unified_pipeline_task(
    query: str,
    driver: Annotated[AsyncDriver, Use(unified_pipeline)],
) -> PipelineQueryResult:
    return await _query(driver, query)
