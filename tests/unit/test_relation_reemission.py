"""#45 — la ré-émission d'une relation existante doit être SILENCIEUSE.

Dogfood 2026-06-12 (Small, Devstral ET Sonnet — structurel) : le relieur ré-émet
les arêtes déjà en base à chaque tour (« LOCATED_AT » 4 fois en 3 tours, doublons
intra-tour sous Sonnet). Le MERGE dédupliquait déjà l'ARÊTE, mais chaque appel
poussait une ToolCard + une ligne de write_log → pollution UI et bruit checker.

Loi testée ici : add_relation sur une arête déjà existante (même paire, même
type — et même verbe_slug pour le narratif) n'émet NI carte NI write_log ; une
arête nouvelle (autre verbe, autre paire, autre projet) émet normalement.

Univers Ostive/Bellac/Vandre — frais, absent de tous les prompts (anti-leakage).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from unittest.mock import MagicMock

from protest import ProTestSuite, Use, fixture
from pydantic_ai import RunContext

from felix.core.deps import GenericDeps
from felix.core.tools import add_relation
from felix.graph.driver import get_driver, setup_constraints

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

relation_reemission_suite = ProTestSuite("RelationReemission")

PROJ = "test-rel-reemission"


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n:GenEntity) WHERE n.project IN [$p, $p2] DETACH DELETE n",
            p=PROJ, p2=PROJ + "-b",
        )


@fixture(max_concurrency=1)
async def _rel_driver() -> AsyncGenerator[AsyncDriver]:
    driver = get_driver()
    await setup_constraints(driver)
    try:
        yield driver
    finally:
        await _wipe(driver)
        await driver.close()


def _make_ctx(driver: AsyncDriver, proj: str = PROJ) -> RunContext[GenericDeps]:
    deps = GenericDeps(driver=driver, project_id=proj)
    ctx = MagicMock(spec=RunContext)
    ctx.deps = deps
    return ctx  # type: ignore[return-value]


async def _seed_pair(driver: AsyncDriver, proj: str = PROJ) -> RunContext[GenericDeps]:
    """Crée Ostive (personnage) et Bellac (lieu) ; renvoie un ctx FRAIS (cartes vides)."""
    async with driver.session() as session:
        for name, etype in (("Ostive", "personnage"), ("Bellac", "lieu")):
            await session.run(
                "MERGE (e:GenEntity {id: $id, project: $project})"
                " SET e.name = $name, e.entity_type = $type",
                id=name.lower(), name=name, type=etype, project=proj,
            )
    return _make_ctx(driver, proj)


@relation_reemission_suite.test()
async def test_structurel_reemis_aucune_carte(
    driver: Annotated[AsyncDriver, Use(_rel_driver)],
) -> None:
    """2e LOCATED_AT identique → ni carte ni write_log (le cas dogfood exact)."""
    await _wipe(driver)
    ctx = await _seed_pair(driver)
    await add_relation(ctx, "Ostive", "Bellac", "LOCATED_AT")
    assert len(ctx.deps.ui_events) == 1
    assert len(ctx.deps.write_log) == 1

    ctx2 = _make_ctx(driver)
    await add_relation(ctx2, "Ostive", "Bellac", "LOCATED_AT")
    assert ctx2.deps.ui_events == [], "ré-émission structurelle → aucune carte"
    assert ctx2.deps.write_log == [], "ré-émission → aucune écriture loggée"


@relation_reemission_suite.test()
async def test_narratif_meme_verbe_silencieux_autre_verbe_emis(
    driver: Annotated[AsyncDriver, Use(_rel_driver)],
) -> None:
    """LIE_A même verbe re-émis → silencieux ; verbe DIFFÉRENT → nouvelle carte (#68)."""
    await _wipe(driver)
    ctx = await _seed_pair(driver)
    await add_relation(ctx, "Ostive", "Bellac", "LIE_A", verbe="surveille")
    assert len(ctx.deps.ui_events) == 1

    ctx2 = _make_ctx(driver)
    await add_relation(ctx2, "Ostive", "Bellac", "LIE_A", verbe="surveille")
    assert ctx2.deps.ui_events == [], "même verbe → silencieux"

    ctx3 = _make_ctx(driver)
    await add_relation(ctx3, "Ostive", "Bellac", "LIE_A", verbe="fuit")
    assert len(ctx3.deps.ui_events) == 1, "autre verbe = autre lien → carte"


@relation_reemission_suite.test()
async def test_reemission_retour_informatif(
    driver: Annotated[AsyncDriver, Use(_rel_driver)],
) -> None:
    """Le retour à l'agent dit que la relation est déjà connue (pas d'invite à rejouer)."""
    await _wipe(driver)
    ctx = await _seed_pair(driver)
    await add_relation(ctx, "Ostive", "Bellac", "LOCATED_AT")
    out = await add_relation(_make_ctx(driver), "Ostive", "Bellac", "LOCATED_AT")
    assert "déjà" in out.lower()


@relation_reemission_suite.test()
async def test_etancheite_projet(
    driver: Annotated[AsyncDriver, Use(_rel_driver)],
) -> None:
    """La même relation dans un AUTRE projet n'est pas une ré-émission."""
    await _wipe(driver)
    ctx_a = await _seed_pair(driver)
    await add_relation(ctx_a, "Ostive", "Bellac", "LOCATED_AT")

    ctx_b = await _seed_pair(driver, PROJ + "-b")
    await add_relation(ctx_b, "Ostive", "Bellac", "LOCATED_AT")
    assert len(ctx_b.deps.ui_events) == 1, "projet distinct → carte émise"
