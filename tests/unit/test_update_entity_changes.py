"""#72 — carte update_entity : « avant → après » pour un champ MODIFIÉ.

Avant ce fix, la carte `Entité mise à jour` traitait toute clé de `to_set`
comme un ajout (« + ajouté »), même quand elle REMPLAÇAIT une valeur déjà
posée (correction explicite, `is_correction=True`) — le front n'avait aucun
moyen d'afficher l'ancienne valeur.

Lois testées (`ToolCard.changes`, cf. `felix.core.models.PropChange`) :
- une modification (valeur existante ET différente) émet un `PropChange`
  (`field`/`before`/`after`) et SORT du texte `added` (plus de doublon) ;
- un AJOUT pur (clé absente/vide avant) n'émet aucun `PropChange` — reste
  dans `added` ;
- une valeur reposée À L'IDENTIQUE n'émet aucun `PropChange` non plus.

Univers Vasnier/Ombreval, frais, absent de tous les prompts.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from unittest.mock import MagicMock

from protest import ProTestSuite, Use, fixture
from pydantic_ai import RunContext

from felix.core.deps import GenericDeps
from felix.core.profile import SCENARIO_PROFILE
from felix.core.tools import add_entity, update_entity
from felix.graph.driver import get_driver, setup_constraints

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

update_entity_changes_suite = ProTestSuite("UpdateEntityChanges")

PROJ = "test-update-entity-changes"


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=PROJ
        )


@fixture(max_concurrency=1)
async def _driver() -> AsyncGenerator[AsyncDriver]:
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


@update_entity_changes_suite.test()
async def test_modification_emet_previous_et_sort_de_added(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Correction explicite d'une valeur existante → PropChange, absent de added."""
    await _wipe(driver)
    ctx = _make_ctx(driver)
    await add_entity(ctx, "Vasnier", "personnage", {"age": "25"})

    ctx2 = _make_ctx(driver)
    await update_entity(ctx2, "Vasnier", {"age": "30"}, is_correction=True)

    card = ctx2.deps.ui_events[-1]
    assert card.changes is not None
    assert len(card.changes) == 1
    change = card.changes[0]
    assert change.field == "age"
    assert change.before == "25"
    assert change.after == "30"
    assert "age" not in card.added, "un champ MODIFIÉ ne doit plus apparaître dans added"


@update_entity_changes_suite.test()
async def test_ajout_pur_pas_de_previous(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Une clé absente avant → simple ajout, aucun PropChange."""
    await _wipe(driver)
    ctx = _make_ctx(driver)
    await add_entity(ctx, "Ombreval", "lieu", {})

    ctx2 = _make_ctx(driver)
    await update_entity(ctx2, "Ombreval", {"climat": "aride"})

    card = ctx2.deps.ui_events[-1]
    assert card.changes is None
    assert "climat" in card.added
    assert "aride" in card.added


@update_entity_changes_suite.test()
async def test_valeur_inchangee_pas_de_previous(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Reposer la MÊME valeur (même en is_correction) n'est pas une modification."""
    await _wipe(driver)
    ctx = _make_ctx(driver)
    await add_entity(ctx, "Vasnier", "personnage", {"age": "25"})

    ctx2 = _make_ctx(driver)
    await update_entity(ctx2, "Vasnier", {"age": "25"}, is_correction=True)

    card = ctx2.deps.ui_events[-1]
    assert card.changes is None


@update_entity_changes_suite.test()
async def test_mixte_ajout_et_modification(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Un même appel qui ajoute ET corrige : les deux cohabitent sans doublon."""
    await _wipe(driver)
    ctx = _make_ctx(driver)
    await add_entity(ctx, "Vasnier", "personnage", {"age": "25"})

    ctx2 = _make_ctx(driver)
    await update_entity(
        ctx2, "Vasnier", {"age": "30", "ville": "Ombreval"}, is_correction=True
    )

    card = ctx2.deps.ui_events[-1]
    assert card.changes is not None
    assert [c.field for c in card.changes] == ["age"]
    assert "age" not in card.added
    assert "ville" in card.added
