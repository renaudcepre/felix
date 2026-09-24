"""Carte entité (#73) : plus de prop arbitraire — « N propriétés · M liens » +
provenance, calculés sans aller-retour par carte ; props internes (`last_touched`)
jamais exposées, ni en liste ni en fiche, une SEULE définition (`INTERNAL_PROPS`).

Univers de test isolé — inédit : atelier de reliure du Corbeau-Gris (relieuse,
presse, cahiers).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from protest import ProTestSuite, Use, fixture

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

from felix.api.models import EntityPatch
from felix.api.routes.entities import get_entity, list_entities, patch_entity
from felix.core.graph import (
    INTERNAL_PROPS,
    RESERVED_KEYS,
    create_entity,
    entity_primary_sources,
    entity_relation_counts,
    link_described_in,
    touch_entities,
)
from felix.graph.driver import get_driver, setup_constraints

entity_list_summary_suite = ProTestSuite("EntityListSummary")

PROJ_A = "test-entity-list-a-v1"
PROJ_B = "test-entity-list-b-v1"


async def _wipe(driver: AsyncDriver, project: str) -> None:
    async with driver.session() as session:
        await session.run("MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=project)


@fixture(max_concurrency=1)
async def _driver() -> AsyncGenerator[AsyncDriver]:
    driver = get_driver()
    await setup_constraints(driver)
    try:
        yield driver
    finally:
        await _wipe(driver, PROJ_A)
        await _wipe(driver, PROJ_B)
        await driver.close()


async def _link(
    driver: AsyncDriver, from_id: str, to_id: str, rel_type: str, *, project: str,
) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (a:GenEntity {id: $a, project: $p}), (b:GenEntity {id: $b, project: $p})"
            " MERGE (a)-[:REL {rel_type: $t}]->(b)",
            a=from_id, b=to_id, t=rel_type, p=project,
        )


def _summary(summaries: list, entity_id: str):
    return next(s for s in summaries if s.id == entity_id)


# ──────────────────── INTERNAL_PROPS : une seule définition ────────────────────

@entity_list_summary_suite.test()
def test_internal_props_contains_last_touched_and_is_disjoint_from_reserved() -> None:
    assert "last_touched" in INTERNAL_PROPS
    assert INTERNAL_PROPS.isdisjoint(RESERVED_KEYS)


# ──────────────────── Fiche (EntityDetail.props) ────────────────────

@entity_list_summary_suite.test()
async def test_last_touched_never_reaches_the_fiche(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver, PROJ_A)
    await create_entity(
        driver, "relieuse-hilde", "Hilde", "personnage", {"metier": "relieuse"}, project=PROJ_A,
    )
    await touch_entities(driver, ["relieuse-hilde"], project=PROJ_A)

    detail = await get_entity("relieuse-hilde", driver, project=PROJ_A)

    assert "last_touched" not in detail.props
    assert detail.props == {"metier": "relieuse"}


@entity_list_summary_suite.test()
async def test_patch_cannot_set_or_remove_last_touched(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Durcissement (#73) : la même définition sert la lecture ET l'écriture
    manuelle — un client qui tenterait de poser/retirer `last_touched` via
    PATCH est ignoré, pas d'exception spéciale à tenir à jour côté front."""
    await _wipe(driver, PROJ_A)
    await create_entity(driver, "presse-corbeau", "Presse", "outil", {}, project=PROJ_A)
    await touch_entities(driver, ["presse-corbeau"], project=PROJ_A)

    await patch_entity(
        "presse-corbeau", EntityPatch(props={"last_touched": "0"}), driver, project=PROJ_A,
    )
    detail = await get_entity("presse-corbeau", driver, project=PROJ_A)
    assert "last_touched" not in detail.props

    async with driver.session() as session:
        result = await session.run(
            "MATCH (e:GenEntity {id: 'presse-corbeau', project: $p}) RETURN e.last_touched AS lt",
            p=PROJ_A,
        )
        record = await result.single()
    assert record is not None
    assert record["lt"] != "0", "le PATCH n'a pas dû écraser last_touched avec une valeur libre"


# ──────────────────── Liste (EntitySummary) ────────────────────

@entity_list_summary_suite.test()
async def test_prop_count_excludes_reserved_and_internal_keys(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver, PROJ_A)
    await create_entity(
        driver, "cahier-un", "Cahier Un", "objet",
        {"matiere": "cuir", "etat": "neuf"}, project=PROJ_A,
    )
    await touch_entities(driver, ["cahier-un"], project=PROJ_A)  # pose last_touched

    summaries = await list_entities(driver, type=None, project=PROJ_A)
    s = _summary(summaries, "cahier-un")
    assert s.prop_count == 2  # matiere + etat, ni id/name/entity_type/project, ni last_touched


@entity_list_summary_suite.test()
async def test_relation_count_excludes_described_in_and_event_machinery(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver, PROJ_A)
    await create_entity(driver, "hilde", "Hilde", "personnage", {}, project=PROJ_A)
    await create_entity(driver, "corvine", "Corvine", "personnage", {}, project=PROJ_A)
    await create_entity(driver, "cahier-annales", "Les Annales", "document", {}, project=PROJ_A)
    # Seul le type importe ici (relation_count doit ignorer l'INVOLVES qui suit) —
    # `ordre`/`resume` d'un vrai événement sont posés EN CODE, pas via `props`
    # (cf. tools.py `add_event`), inutiles pour ce test.
    await create_entity(driver, "event-un", "réunion", "evenement", {}, project=PROJ_A)
    await _link(driver, "hilde", "corvine", "CONNAIT", project=PROJ_A)
    await link_described_in(driver, ["hilde"], "cahier-annales", 1, project=PROJ_A)
    await _link(driver, "event-un", "hilde", "INVOLVES", project=PROJ_A)

    summaries = await list_entities(driver, type=None, project=PROJ_A)
    s = _summary(summaries, "hilde")
    assert s.relation_count == 1, "CONNAIT compte, DESCRIBED_IN et INVOLVES non"


@entity_list_summary_suite.test()
async def test_source_is_none_without_described_in(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver, PROJ_A)
    await create_entity(driver, "orpheline", "Orpheline", "personnage", {}, project=PROJ_A)

    summaries = await list_entities(driver, type=None, project=PROJ_A)
    assert _summary(summaries, "orpheline").source is None


@entity_list_summary_suite.test()
async def test_source_is_title_and_sorted_pages_of_first_document(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Deux documents décrivent la même entité : on ne garde QUE le premier
    (id document trié — déterministe), et les pages sont triées même si
    posées dans le désordre."""
    await _wipe(driver, PROJ_A)
    await create_entity(driver, "corvine", "Corvine", "personnage", {}, project=PROJ_A)
    await create_entity(driver, "doc-a", "Cahier des annales", "document", {}, project=PROJ_A)
    await create_entity(driver, "doc-b", "Registre secondaire", "document", {}, project=PROJ_A)
    # Pages posées dans le désordre + document B lié en premier (l'ordre d'écriture
    # ne doit pas décider — seul l'id du document, trié, décide du "premier").
    await link_described_in(driver, ["corvine"], "doc-b", 1, project=PROJ_A)
    await link_described_in(driver, ["corvine"], "doc-a", 3, project=PROJ_A)
    await link_described_in(driver, ["corvine"], "doc-a", 1, project=PROJ_A)
    await link_described_in(driver, ["corvine"], "doc-a", 2, project=PROJ_A)

    summaries = await list_entities(driver, type=None, project=PROJ_A)
    source = _summary(summaries, "corvine").source
    assert source is not None
    assert source.title == "Cahier des annales"
    assert source.pages == [1, 2, 3]


# ──────────────────── Isolation projet ────────────────────

@entity_list_summary_suite.test()
async def test_counts_and_source_are_project_isolated(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver, PROJ_A)
    await _wipe(driver, PROJ_B)
    # Même id d'entité dans les deux projets, contenu très différent.
    await create_entity(
        driver, "carnet", "Carnet", "objet", {"couleur": "rouge"}, project=PROJ_A,
    )
    await create_entity(driver, "carnet", "Carnet", "objet", {}, project=PROJ_B)
    await create_entity(driver, "corvine", "Corvine", "personnage", {}, project=PROJ_A)
    await create_entity(driver, "doc-a", "Cahier A", "document", {}, project=PROJ_A)
    await _link(driver, "carnet", "corvine", "APPARTIENT_A", project=PROJ_A)
    await link_described_in(driver, ["carnet"], "doc-a", 1, project=PROJ_A)

    summaries_a = await list_entities(driver, type=None, project=PROJ_A)
    summaries_b = await list_entities(driver, type=None, project=PROJ_B)
    carnet_a = _summary(summaries_a, "carnet")
    carnet_b = _summary(summaries_b, "carnet")

    assert carnet_a.prop_count == 1
    assert carnet_a.relation_count == 1
    assert carnet_a.source is not None and carnet_a.source.title == "Cahier A"

    assert carnet_b.prop_count == 0
    assert carnet_b.relation_count == 0
    assert carnet_b.source is None


@entity_list_summary_suite.test()
async def test_entity_relation_counts_and_primary_sources_are_project_isolated(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Même garantie directement sur les helpers `graph.py` (une requête pour
    tout le projet, jamais par carte) — pas seulement via la route."""
    await _wipe(driver, PROJ_A)
    await _wipe(driver, PROJ_B)
    await create_entity(driver, "levier", "Levier", "piece", {}, project=PROJ_A)
    await create_entity(driver, "levier", "Levier", "piece", {}, project=PROJ_B)
    await create_entity(driver, "presse", "Presse", "outil", {}, project=PROJ_A)
    await create_entity(driver, "doc-a", "Manuel A", "document", {}, project=PROJ_A)
    await _link(driver, "levier", "presse", "PART_OF", project=PROJ_A)
    await link_described_in(driver, ["levier"], "doc-a", 1, project=PROJ_A)

    counts_a = await entity_relation_counts(driver, project=PROJ_A, excluded_rel_types=set())
    counts_b = await entity_relation_counts(driver, project=PROJ_B, excluded_rel_types=set())
    assert counts_a["levier"] == 2  # PART_OF + DESCRIBED_IN, rien exclu ici
    assert counts_b["levier"] == 0

    sources_a = await entity_primary_sources(driver, project=PROJ_A)
    sources_b = await entity_primary_sources(driver, project=PROJ_B)
    assert sources_a["levier"]["title"] == "Manuel A"
    assert "levier" not in sources_b
