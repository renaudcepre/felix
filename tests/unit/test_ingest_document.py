"""Ingestion de document (Étape 2) — fonctions PURES (lecture/nettoyage/découpe)
et le graphe helper `link_described_in`. Fixture SX-40 (sertisseuse synthétique,
cf. [[feedback_prompt_test_leakage]]) — 4 pages, en-tête sur page 1 seulement,
pied de page répété sur les 4.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from unittest.mock import MagicMock

from protest import ProTestSuite, Use, fixture, tmp_path
from pydantic_ai import RunContext

from felix.core.deps import GenericDeps
from felix.core.graph import link_described_in
from felix.core.profile import MAINTENANCE_PROFILE
from felix.core.tools import add_relation
from felix.graph.driver import get_driver, setup_constraints
from felix.ingest.document import (
    Chunk,
    chunk_pages,
    clean_pages,
    entity_pages,
    guess_title,
    pages_mentioning,
    read_pages,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

ingest_document_suite = ProTestSuite("IngestDocument")

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "evals" / "maintenance" / "fixtures" / "sx40_fiche.txt"
)

PROJ = "test-ingest-document"


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=PROJ,
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
    deps = GenericDeps(driver=driver, project_id=PROJ, profile=MAINTENANCE_PROFILE)
    ctx = MagicMock(spec=RunContext)
    ctx.deps = deps
    return ctx  # type: ignore[return-value]


# ──────────────────── read_pages ────────────────────
@ingest_document_suite.test()
def test_read_pages_splits_on_form_feed() -> None:
    pages = read_pages(FIXTURE)
    assert len(pages) == 4


@ingest_document_suite.test()
def test_read_pages_single_page_without_form_feed(
    tmp: Annotated[Path, Use(tmp_path)],
) -> None:
    p = tmp / "note.txt"
    p.write_text("bonjour, une seule page", encoding="utf-8")
    assert read_pages(p) == ["bonjour, une seule page"]


@ingest_document_suite.test()
def test_read_pages_md_same_as_txt(tmp: Annotated[Path, Use(tmp_path)]) -> None:
    p = tmp / "note.md"
    p.write_text("page a\fpage b", encoding="utf-8")
    assert read_pages(p) == ["page a", "page b"]


# ──────────────────── clean_pages ────────────────────
@ingest_document_suite.test()
def test_clean_pages_removes_repeated_footer() -> None:
    cleaned = clean_pages(read_pages(FIXTURE))
    joined = "\n".join(cleaned)
    assert "Édité avec DocuFab" not in joined


@ingest_document_suite.test()
def test_clean_pages_removes_page_number_lines() -> None:
    cleaned = clean_pages(read_pages(FIXTURE))
    joined = "\n".join(cleaned)
    assert "Page 1 sur 4" not in joined
    assert "Page 4 sur 4" not in joined


@ingest_document_suite.test()
def test_clean_pages_keeps_header_only_on_first_page() -> None:
    """L'en-tête n'apparaît QUE sur la page 1 (25 % des pages < seuil 50 %) —
    il est donc GARDÉ, à la différence du pied de page répété sur les 4."""
    cleaned = clean_pages(read_pages(FIXTURE))
    assert "Fiche réglage sertisseuse SX-40" in cleaned[0]
    for page in cleaned[1:]:
        assert "Fiche réglage sertisseuse SX-40" not in page


@ingest_document_suite.test()
def test_clean_pages_collapses_blank_runs() -> None:
    cleaned = clean_pages(["a\n\n\n\n\nb", "x", "y"])
    assert "\n\n\n" not in cleaned[0]


@ingest_document_suite.test()
def test_clean_pages_below_three_pages_skips_repetition_rule() -> None:
    """Sous 3 pages, le seuil de répétition ne s'applique pas (le plan le
    réserve explicitement à « au moins 3 pages ») — seules les lignes de
    numérotation sont retirées."""
    pages = ["identique\ncontenu A", "identique\ncontenu B"]
    cleaned = clean_pages(pages)
    assert "identique" in cleaned[0]
    assert "identique" in cleaned[1]


# ──────────────────── chunk_pages / Chunk.prompt ────────────────────
@ingest_document_suite.test()
def test_chunk_pages_merges_small_consecutive_pages() -> None:
    chunks = chunk_pages(["petite page 1", "petite page 2", "petite page 3"], max_chars=3000)
    assert len(chunks) == 1
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 3


@ingest_document_suite.test()
def test_chunk_pages_keeps_one_chunk_per_substantial_page() -> None:
    # Attribution de page = la valeur RAG : deux pages de contenu réel ne sont
    # PAS fusionnées, sinon chaque fiche pointe vers « pages 1-2 » au lieu de sa page.
    page = "Force de sertissage : 8 à 15 kN. " * 12
    chunks = chunk_pages([page, page], max_chars=3000, min_chars=300)
    assert [(c.page_start, c.page_end) for c in chunks] == [(1, 1), (2, 2)]


@ingest_document_suite.test()
def test_chunk_pages_splits_oversize_page_on_paragraph_boundary() -> None:
    para_a = "A" * 2000
    para_b = "B" * 2000
    page = f"{para_a}\n\n{para_b}"
    chunks = chunk_pages([page], max_chars=3000)
    assert len(chunks) == 2
    assert chunks[0].text == para_a
    assert chunks[1].text == para_b
    assert chunks[0].page_start == chunks[0].page_end == 1
    assert chunks[1].page_start == chunks[1].page_end == 1


@ingest_document_suite.test()
def test_chunk_pages_skips_blank_pages() -> None:
    chunks = chunk_pages(["contenu", "", "   ", "suite"], max_chars=3000)
    assert len(chunks) == 1
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 4


@ingest_document_suite.test()
def test_chunk_prompt_single_page() -> None:
    chunk = Chunk(page_start=2, page_end=2, text="contenu")
    rendered = chunk.prompt("Fiche SX-40", 4)
    assert "« Fiche SX-40 »" in rendered
    assert "(page 2/4)" in rendered
    assert "contenu" in rendered


@ingest_document_suite.test()
def test_chunk_prompt_page_range() -> None:
    chunk = Chunk(page_start=2, page_end=3, text="contenu")
    rendered = chunk.prompt("Fiche SX-40", 4)
    assert "(pages 2-3/4)" in rendered


# ──────────────────── guess_title ────────────────────
@ingest_document_suite.test()
def test_guess_title_first_meaningful_line() -> None:
    assert guess_title(["", "  \n  premier titre\nsuite"], "repli") == "premier titre"


@ingest_document_suite.test()
def test_guess_title_fallback_on_empty_pages() -> None:
    assert guess_title(["", "   \n  "], "sx40_fiche") == "sx40_fiche"


@ingest_document_suite.test()
def test_guess_title_on_sx40_fixture() -> None:
    cleaned = clean_pages(read_pages(FIXTURE))
    assert guess_title(cleaned, "repli") == "Fiche réglage sertisseuse SX-40 — Version 3"


# ──────────────────── add_relation refuse DESCRIBED_IN (code_only_relations) ────
@ingest_document_suite.test()
async def test_add_relation_refuses_described_in() -> None:
    """DESCRIBED_IN est posée PAR LE CODE (link_described_in) à l'ingestion —
    l'agent LLM qui tente de la poser via add_relation est refusé, AVANT même
    la résolution des entités (aucun accès driver nécessaire pour le refus)."""
    ctx = _make_ctx(driver=None)  # type: ignore[arg-type]
    out = await add_relation(ctx, "pédale", "fiche SX-40", "DESCRIBED_IN")
    assert "code" in out.lower()
    assert ctx.deps.ui_events == []
    assert ctx.deps.write_log == []


# ──────────────────── link_described_in (Neo4j) ────────────────────
@ingest_document_suite.test()
async def test_link_described_in_creates_relation_with_page(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    async with driver.session() as session:
        for eid, name, etype in (
            ("pedale-sx40", "pédale SX-40", "commande"),
            ("fiche-sx40", "Fiche SX-40", "document"),
        ):
            await session.run(
                "MERGE (e:GenEntity {id: $id, project: $project})"
                " SET e.name = $name, e.entity_type = $type",
                id=eid, name=name, type=etype, project=PROJ,
            )
    await link_described_in(driver, ["pedale-sx40"], "fiche-sx40", 2, project=PROJ)

    async with driver.session() as session:
        result = await session.run(
            "MATCH (:GenEntity {id: 'pedale-sx40', project: $p})"
            "-[r:REL {rel_type: 'DESCRIBED_IN'}]->(:GenEntity {id: 'fiche-sx40', project: $p})"
            " RETURN r.pages AS pages",
            p=PROJ,
        )
        record = await result.single()
    assert record is not None
    assert record["pages"] == [2]


@ingest_document_suite.test()
async def test_link_described_in_appends_new_page_idempotently(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    async with driver.session() as session:
        for eid, name, etype in (
            ("mors-sx40", "mors SX-40", "organe"),
            ("fiche-sx40", "Fiche SX-40", "document"),
        ):
            await session.run(
                "MERGE (e:GenEntity {id: $id, project: $project})"
                " SET e.name = $name, e.entity_type = $type",
                id=eid, name=name, type=etype, project=PROJ,
            )
    await link_described_in(driver, ["mors-sx40"], "fiche-sx40", 2, project=PROJ)
    await link_described_in(driver, ["mors-sx40"], "fiche-sx40", 3, project=PROJ)
    await link_described_in(driver, ["mors-sx40"], "fiche-sx40", 2, project=PROJ)  # rejoué

    async with driver.session() as session:
        result = await session.run(
            "MATCH (:GenEntity {id: 'mors-sx40', project: $p})"
            "-[r:REL {rel_type: 'DESCRIBED_IN'}]->(:GenEntity {id: 'fiche-sx40', project: $p})"
            " RETURN r.pages AS pages",
            p=PROJ,
        )
        record = await result.single()
    assert record["pages"] == [2, 3]


@ingest_document_suite.test()
async def test_link_described_in_excludes_document_itself(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Le document ne se décrit jamais dans lui-même (filtré par l'appelant)."""
    await _wipe(driver)
    async with driver.session() as session:
        await session.run(
            "MERGE (e:GenEntity {id: 'fiche-sx40', project: $p})"
            " SET e.name = 'Fiche SX-40', e.entity_type = 'document'",
            p=PROJ,
        )
    await link_described_in(driver, ["fiche-sx40"], "fiche-sx40", 1, project=PROJ)

    async with driver.session() as session:
        result = await session.run(
            "MATCH (:GenEntity {id: 'fiche-sx40', project: $p})"
            "-[r:REL {rel_type: 'DESCRIBED_IN'}]->(:GenEntity {project: $p})"
            " RETURN count(r) AS n",
            p=PROJ,
        )
        record = await result.single()
    assert record["n"] == 0


# ──────────────────── pages_mentioning : attribution de page en code ────────────────────
# Le LLM lit le document ENTIER (contexte = qualité) ; la page d'une fiche est
# retrouvée par le code, en cherchant son nom ou ses valeurs dans le texte des pages.
_SX40_PAGES = {
    2: "Bouton START (vert) : lance le cycle.\nBouton STOP (rouge) : arrêt.",
    3: "Pression d'approche : 2 à 6 bars.\nVoyant orange : pression hors plage.",
    4: "La course de sertissage se règle par crans : 1 cran = 0,5 mm.",
}


@ingest_document_suite.test()
def test_pages_mentioning_finds_name_case_and_accent_insensitive() -> None:
    assert pages_mentioning(["bouton start"], _SX40_PAGES) == [2]
    assert pages_mentioning(["Pression d'approche"], _SX40_PAGES) == [3]
    assert pages_mentioning(["Pression dapproche"], _SX40_PAGES) == [3]  # tolère une coquille


@ingest_document_suite.test()
def test_pages_mentioning_uses_property_values_when_name_is_invented() -> None:
    # Nom forgé par le modèle, absent du texte ; sa valeur verbatim, elle, y est.
    assert pages_mentioning(["Réglage de course", "1 cran = 0,5 mm"], _SX40_PAGES) == [4]


@ingest_document_suite.test()
def test_pages_mentioning_ignores_short_noise_and_returns_empty_when_absent() -> None:
    assert pages_mentioning(["à", "3", ""], _SX40_PAGES) == []
    assert pages_mentioning(["Mâchoire inférieure"], _SX40_PAGES) == []


@ingest_document_suite.test()
def test_entity_pages_prefers_name_over_loose_property_matches() -> None:
    # Vu en live : « à gauche du pupitre » (prop) matchait flou la page 1
    # (« les boutons du pupitre ») → Bouton START attribué pages 1-3 au lieu de 2.
    pages = {1: "Cette fiche couvre les boutons du pupitre.", **_SX40_PAGES}
    node = {"id": "bouton-start", "name": "Bouton START",
            "emplacement": "à gauche du pupitre", "role": "lance le cycle"}
    assert entity_pages(node, pages) == [2]


@ingest_document_suite.test()
def test_entity_pages_falls_back_to_properties_then_to_all_pages() -> None:
    node = {"id": "x", "name": "Réglage de course", "valeur": "1 cran = 0,5 mm"}
    assert entity_pages(node, _SX40_PAGES) == [4]
    ghost = {"id": "y", "name": "Mâchoire inférieure"}
    assert entity_pages(ghost, _SX40_PAGES) == [2, 3, 4]
