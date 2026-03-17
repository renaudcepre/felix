from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from neo4j import AsyncDriver

from felix.graph.driver import get_driver, setup_constraints
from felix.graph.seed import seed_graph


@pytest.fixture
async def driver() -> AsyncGenerator[AsyncDriver]:
    drv = get_driver()
    await setup_constraints(drv)
    yield drv
    await drv.close()


@pytest.fixture
async def seeded_driver(driver: AsyncDriver) -> AsyncGenerator[AsyncDriver]:
    await seed_graph(driver)
    yield driver
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
