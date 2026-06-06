from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from neo4j import AsyncDriver
from protest import Use, fixture

from felix.graph.driver import get_driver, setup_constraints
from felix.graph.seed import seed_graph


@fixture(tags=["neo4j"])
async def neo4j_driver() -> AsyncIterator[AsyncDriver]:
    drv = get_driver()
    await setup_constraints(drv)
    yield drv
    await drv.close()


@fixture(max_concurrency=1, tags=["neo4j"])
async def seeded_driver(
    driver: Annotated[AsyncDriver, Use(neo4j_driver)],
) -> AsyncIterator[AsyncDriver]:
    await seed_graph(driver)
    yield driver
    async with driver.session() as s:
        await s.run("MATCH (n) DETACH DELETE n")
