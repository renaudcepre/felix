from __future__ import annotations

from neo4j import AsyncDriver, AsyncGraphDatabase

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
    """Create constraints and indexes if they don't exist.

    Modèle 100 % schemaless : une seule contrainte d'unicité sur l'id des
    :GenEntity. Les anciennes contraintes legacy (:Character/:Scene/…) déjà
    créées en base sont inertes (plus aucun code ne les lit)."""
    statements = [
        "CREATE CONSTRAINT genentity_id_unique IF NOT EXISTS FOR (e:GenEntity) REQUIRE e.id IS UNIQUE",
    ]
    async with driver.session() as session:
        for stmt in statements:
            await session.run(stmt)


async def close_driver(driver: AsyncDriver) -> None:
    """Close the driver and release all connections."""
    await driver.close()
