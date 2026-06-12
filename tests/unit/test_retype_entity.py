"""#75 — retype_entity : corriger le TYPE d'une entité existante.

Dogfood 2026-06-12 (cas Klarkz, vu sous Devstral ET Sonnet) : « X n'est pas un
lieu mais un minerai » n'avait AUCUN chemin d'exécution — update_entity ne touche
pas entity_type, les modèles bricolaient une prop (`type='minerais'`,
`type_entite_corrige='objet'`) sur une entité qui restait un lieu, et le checker
alertait en boucle.

Lois testées :
- le retypage change `entity_type` en base, émet une carte et nourrit le checker
  (write_log + check_candidates : l'alerte doit pouvoir s'éteindre) ;
- les gardes de création sont REJOUÉES sur le nouveau type (evenement réservé,
  anti-état #64) — refus terminal, type INCHANGÉ ;
- les relations structurelles devenues invalides (domaine/portée du nouveau
  type) sont SIGNALÉES dans le retour, jamais supprimées (témoignage) ;
- retypage vers le type actuel = retour informatif sans effet.

Univers Quillon/Darnave/Solmer — frais, absent de tous les prompts.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from unittest.mock import MagicMock

from protest import ProTestSuite, Use, fixture
from pydantic_ai import RunContext

from felix.core.deps import GenericDeps
from felix.core.profile import SCENARIO_PROFILE
from felix.core.tools import add_relation, retype_entity
from felix.graph.driver import get_driver, setup_constraints

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

retype_entity_suite = ProTestSuite("RetypeEntity")

PROJ = "test-retype-entity"


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=PROJ
        )


@fixture(max_concurrency=1)
async def _retype_driver() -> AsyncGenerator[AsyncDriver]:
    driver = get_driver()
    await setup_constraints(driver)
    try:
        yield driver
    finally:
        await _wipe(driver)
        await driver.close()


def _make_ctx(driver: AsyncDriver) -> RunContext[GenericDeps]:
    deps = GenericDeps(driver=driver, profile=SCENARIO_PROFILE, project_id=PROJ)
    ctx = MagicMock(spec=RunContext)
    ctx.deps = deps
    return ctx  # type: ignore[return-value]


async def _seed(driver: AsyncDriver, name: str, etype: str) -> None:
    async with driver.session() as session:
        await session.run(
            "MERGE (e:GenEntity {id: $id, project: $project})"
            " SET e.name = $name, e.entity_type = $type",
            id=name.lower(), name=name, type=etype, project=PROJ,
        )


async def _type_of(driver: AsyncDriver, name: str) -> str:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (e:GenEntity {id: $id, project: $p}) RETURN e.entity_type AS t",
            id=name.lower(), p=PROJ,
        )
        record = await result.single()
        return record["t"] if record else "?"


@retype_entity_suite.test()
async def test_retypage_nominal(
    driver: Annotated[AsyncDriver, Use(_retype_driver)],
) -> None:
    """lieu → objet : type changé, carte émise, checker nourri (cas Klarkz)."""
    await _wipe(driver)
    await _seed(driver, "Quillon", "lieu")
    ctx = _make_ctx(driver)
    out = await retype_entity(ctx, "Quillon", "objet")
    assert await _type_of(driver, "Quillon") == "objet"
    assert "objet" in out
    assert len(ctx.deps.ui_events) == 1
    assert ctx.deps.write_log, "le retypage est une écriture : le checker doit le voir"
    assert "quillon" in ctx.deps.check_candidates, "l'alerte doit pouvoir s'éteindre"


@retype_entity_suite.test()
async def test_refus_type_reserve_evenement(
    driver: Annotated[AsyncDriver, Use(_retype_driver)],
) -> None:
    """Retypage vers 'evenement' → refus (garde rejouée), type INCHANGÉ."""
    await _wipe(driver)
    await _seed(driver, "Quillon", "lieu")
    ctx = _make_ctx(driver)
    await retype_entity(ctx, "Quillon", "evenement")
    assert await _type_of(driver, "Quillon") == "lieu", "refus → aucun effet"
    assert ctx.deps.ui_events == []


@retype_entity_suite.test()
async def test_refus_anti_etat(
    driver: Annotated[AsyncDriver, Use(_retype_driver)],
) -> None:
    """Retypage vers 'maladie' (#64) → refus, type INCHANGÉ."""
    await _wipe(driver)
    await _seed(driver, "Quillon", "objet")
    ctx = _make_ctx(driver)
    await retype_entity(ctx, "Quillon", "maladie")
    assert await _type_of(driver, "Quillon") == "objet"
    assert ctx.deps.ui_events == []


@retype_entity_suite.test()
async def test_meme_type_sans_effet(
    driver: Annotated[AsyncDriver, Use(_retype_driver)],
) -> None:
    """Retypage vers le type actuel → retour informatif, aucune carte."""
    await _wipe(driver)
    await _seed(driver, "Quillon", "objet")
    ctx = _make_ctx(driver)
    out = await retype_entity(ctx, "Quillon", "objet")
    assert "déjà" in out.lower()
    assert ctx.deps.ui_events == []


@retype_entity_suite.test()
async def test_relations_invalides_signalees(
    driver: Annotated[AsyncDriver, Use(_retype_driver)],
) -> None:
    """Darnave LOCATED_AT Quillon(lieu) ; Quillon → objet ⇒ l'arête devenue
    invalide (LOCATED_AT exige un lieu en objet) est SIGNALÉE, pas supprimée."""
    await _wipe(driver)
    await _seed(driver, "Quillon", "lieu")
    await _seed(driver, "Darnave", "personnage")
    await add_relation(_make_ctx(driver), "Darnave", "Quillon", "LOCATED_AT")

    ctx = _make_ctx(driver)
    out = await retype_entity(ctx, "Quillon", "objet")
    assert "LOCATED_AT" in out, "la relation devenue invalide est signalée"
    # Témoignage : rien n'est supprimé.
    async with driver.session() as session:
        result = await session.run(
            "MATCH (:GenEntity {id: 'darnave', project: $p})-[r:REL]->"
            "(:GenEntity {id: 'quillon', project: $p}) RETURN count(r) AS n",
            p=PROJ,
        )
        record = await result.single()
        assert record["n"] == 1, "l'arête est conservée (témoignage)"


@retype_entity_suite.test()
async def test_introuvable(
    driver: Annotated[AsyncDriver, Use(_retype_driver)],
) -> None:
    """Entité inconnue → message, aucun effet."""
    await _wipe(driver)
    ctx = _make_ctx(driver)
    out = await retype_entity(ctx, "Solmer", "objet")
    assert "existe pas" in out
    assert ctx.deps.ui_events == []
