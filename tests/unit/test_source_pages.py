"""Texte source persisté par page (:SourcePage, #vérif-source) — persistance à
l'ingestion (idempotente) et lecture via DESCRIBED_IN, isolation projet.

Sans cette persistance, le vérificateur (`felix.core.check.verify_against_source`)
ne pourrait relire la source QUE pendant l'ingestion elle-même — une alerte levée
plus tard (tour de chat, sur une fiche déjà en base) resterait « unverifiable »
pour toujours, même si le document existe.

Noms univers isolé pour ces tests — inédits : Verrun, Oskad.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from protest import ProTestSuite, Use, fixture

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

from felix.core.graph import create_entity, link_described_in
from felix.core.source_pages import persist_source_pages, source_pages_for
from felix.graph.driver import get_driver, setup_constraints

source_pages_suite = ProTestSuite("SourcePages")

PROJ_A = "test-source-pages-a-v1"
PROJ_B = "test-source-pages-b-v1"


async def _wipe(driver: AsyncDriver, project: str) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=project
        )
        await session.run(
            "MATCH (n:SourcePage {project: $p}) DETACH DELETE n", p=project
        )


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


# ──────────────────── persist_source_pages ────────────────────


@source_pages_suite.test()
async def test_persist_source_pages_creates_one_node_per_nonblank_page(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver, PROJ_A)
    await persist_source_pages(
        driver, "doc-verrun", ["page un", "", "   ", "page quatre"], project=PROJ_A
    )
    async with driver.session() as session:
        result = await session.run(
            "MATCH (sp:SourcePage {project: $p, document_id: 'doc-verrun'})"
            " RETURN sp.page AS page, sp.text AS text ORDER BY sp.page",
            p=PROJ_A,
        )
        rows = await result.data()
    assert [(r["page"], r["text"]) for r in rows] == [
        (1, "page un"),
        (4, "page quatre"),
    ]


@source_pages_suite.test()
async def test_persist_source_pages_is_idempotent_and_updates_text(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver, PROJ_A)
    await persist_source_pages(driver, "doc-oskad", ["texte initial"], project=PROJ_A)
    await persist_source_pages(driver, "doc-oskad", ["texte corrigé"], project=PROJ_A)
    async with driver.session() as session:
        result = await session.run(
            "MATCH (sp:SourcePage {project: $p, document_id: 'doc-oskad'}) RETURN sp.text AS text",
            p=PROJ_A,
        )
        rows = await result.data()
    assert [r["text"] for r in rows] == ["texte corrigé"], (
        "MERGE doit mettre à jour, pas dupliquer"
    )


@source_pages_suite.test()
async def test_persist_source_pages_noop_on_all_blank_pages(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver, PROJ_A)
    await persist_source_pages(driver, "doc-vide", ["", "   "], project=PROJ_A)
    async with driver.session() as session:
        result = await session.run(
            "MATCH (sp:SourcePage {project: $p, document_id: 'doc-vide'}) RETURN count(sp) AS n",
            p=PROJ_A,
        )
        record = await result.single()
    assert record["n"] == 0


# ──────────────────── source_pages_for ────────────────────


@source_pages_suite.test()
async def test_source_pages_for_returns_page_text_via_described_in(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver, PROJ_A)
    await create_entity(
        driver, "fiche-verrun", "Fiche Verrun", "document", {}, project=PROJ_A
    )
    await create_entity(
        driver, "levier-verrun", "levier Verrun", "organe", {}, project=PROJ_A
    )
    await persist_source_pages(
        driver,
        "fiche-verrun",
        ["page un", "le levier Verrun se règle en page deux"],
        project=PROJ_A,
    )
    await link_described_in(
        driver, ["levier-verrun"], "fiche-verrun", 2, project=PROJ_A
    )

    pages = await source_pages_for(driver, ["levier-verrun"], project=PROJ_A)
    assert pages == [("Fiche Verrun", 2, "le levier Verrun se règle en page deux")]


@source_pages_suite.test()
async def test_source_pages_for_empty_when_no_described_in(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver, PROJ_A)
    await create_entity(
        driver, "orphelin-verrun", "orphelin Verrun", "organe", {}, project=PROJ_A
    )
    assert await source_pages_for(driver, ["orphelin-verrun"], project=PROJ_A) == []


@source_pages_suite.test()
async def test_source_pages_for_empty_ids_short_circuits(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    assert await source_pages_for(driver, [], project=PROJ_A) == []


@source_pages_suite.test()
async def test_source_pages_for_project_isolation(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Un document de l'histoire A ne doit jamais alimenter la vérification
    d'une entité de l'histoire B, même avec le même id d'entité des deux côtés."""
    await _wipe(driver, PROJ_A)
    await _wipe(driver, PROJ_B)
    await create_entity(
        driver, "fiche-oskad", "Fiche Oskad", "document", {}, project=PROJ_A
    )
    await create_entity(
        driver, "piece-oskad", "pièce Oskad", "organe", {}, project=PROJ_A
    )
    await persist_source_pages(
        driver, "fiche-oskad", ["texte histoire A"], project=PROJ_A
    )
    await link_described_in(driver, ["piece-oskad"], "fiche-oskad", 1, project=PROJ_A)

    # Même id d'entité dans l'histoire B, mais SANS DESCRIBED_IN ni SourcePage.
    await create_entity(
        driver, "piece-oskad", "pièce Oskad (B)", "organe", {}, project=PROJ_B
    )

    pages_b = await source_pages_for(driver, ["piece-oskad"], project=PROJ_B)
    assert pages_b == [], "le texte source de l'histoire A a fuité dans l'histoire B"
    pages_a = await source_pages_for(driver, ["piece-oskad"], project=PROJ_A)
    assert pages_a == [("Fiche Oskad", 1, "texte histoire A")]
