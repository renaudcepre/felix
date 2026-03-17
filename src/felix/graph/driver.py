from __future__ import annotations

from neo4j import AsyncGraphDatabase, AsyncDriver

from felix.config import settings


def get_driver(
    uri: str | None = None,
    user: str | None = None,
    password: str | None = None,
) -> AsyncDriver:
    """Create and return an AsyncDriver instance."""
    return AsyncGraphDatabase.driver(
        uri or settings.neo4j_uri,
        auth=(user or settings.neo4j_user, password or settings.neo4j_password),
    )


async def setup_constraints(driver: AsyncDriver) -> None:
    """Create all constraints and indexes if they don't exist."""
    statements = [
        "CREATE CONSTRAINT char_id_unique   IF NOT EXISTS FOR (c:Character)    REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT loc_id_unique    IF NOT EXISTS FOR (l:Location)      REQUIRE l.id IS UNIQUE",
        "CREATE CONSTRAINT scene_id_unique  IF NOT EXISTS FOR (s:Scene)         REQUIRE s.id IS UNIQUE",
        "CREATE CONSTRAINT event_id_unique  IF NOT EXISTS FOR (e:TimelineEvent) REQUIRE e.id IS UNIQUE",
        "CREATE CONSTRAINT issue_id_unique  IF NOT EXISTS FOR (i:Issue)         REQUIRE i.id IS UNIQUE",
        "CREATE CONSTRAINT fact_id_unique   IF NOT EXISTS FOR (f:Fact)          REQUIRE f.id IS UNIQUE",
        "CREATE INDEX char_name  IF NOT EXISTS FOR (c:Character)    ON (c.name)",
        "CREATE INDEX scene_date IF NOT EXISTS FOR (s:Scene)        ON (s.date)",
        "CREATE INDEX scene_era  IF NOT EXISTS FOR (s:Scene)        ON (s.era)",
        "CREATE INDEX issue_type IF NOT EXISTS FOR (i:Issue)        ON (i.type)",
        "CREATE INDEX fact_type  IF NOT EXISTS FOR (f:Fact)         ON (f.type)",
    ]
    async with driver.session() as session:
        for stmt in statements:
            await session.run(stmt)


async def close_driver(driver: AsyncDriver) -> None:
    """Close the driver and release all connections."""
    await driver.close()
