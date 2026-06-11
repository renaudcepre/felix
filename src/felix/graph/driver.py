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

    Modèle 100 % schemaless, scopé par projet (#60) : l'ancienne contrainte
    d'unicité GLOBALE sur e.id est incompatible avec la clé composite
    {id, project} (deux histoires ont chacune leur « camille ») → on la DROP.
    L'unicité vit dans les clés de MERGE des writers (Community : pas de
    contrainte composite). L'index (project, id) porte les lookups scopés.
    Les anciennes contraintes legacy (:Character/:Scene/…) déjà créées en base
    sont inertes (plus aucun code ne les lit)."""
    statements = [
        "DROP CONSTRAINT genentity_id_unique IF EXISTS",
        "CREATE INDEX genentity_project_id IF NOT EXISTS"
        " FOR (e:GenEntity) ON (e.project, e.id)",
        "CREATE INDEX project_id IF NOT EXISTS FOR (p:Project) ON (p.id)",
    ]
    async with driver.session() as session:
        for stmt in statements:
            await session.run(stmt)


async def close_driver(driver: AsyncDriver) -> None:
    """Close the driver and release all connections."""
    await driver.close()
