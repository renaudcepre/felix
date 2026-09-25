"""Ingestion de document (Étape 2) — fonctions PURES (lecture/nettoyage/découpe)
et le graphe helper `link_described_in`. Fixture SX-40 (sertisseuse synthétique,
cf. [[feedback_prompt_test_leakage]]) — 4 pages, en-tête sur page 1 seulement,
pied de page répété sur les 4.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from unittest.mock import MagicMock, patch

import httpx
from fastapi import FastAPI
from protest import ProTestSuite, Use, fixture, tmp_path
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel
from pypdf import PdfWriter
from sse_starlette import ServerSentEvent

from felix.api import deps as api_deps
from felix.api.routes import ingest as ingest_routes
from felix.core.deps import GenericDeps
from felix.core.graph import link_described_in
from felix.core.profile import MAINTENANCE_PROFILE
from felix.core.tools import add_relation
from felix.graph.driver import get_driver, setup_constraints
from felix.ingest.document import (
    Chunk,
    IngestReport,
    chunk_pages,
    clean_pages,
    entity_pages,
    guess_title,
    ingest_document,
    is_document_duplicate,
    merge_document_duplicates,
    pages_mentioning,
    read_pages,
    read_title,
    stream_ingest_document,
)
from felix.ingest.resolver import slugify

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

ingest_document_suite = ProTestSuite("IngestDocument")

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "evals"
    / "maintenance"
    / "fixtures"
    / "sx40_fiche.txt"
)

PROJ = "test-ingest-document"


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n:GenEntity {project: $p}) DETACH DELETE n",
            p=PROJ,
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
    chunks = chunk_pages(
        ["petite page 1", "petite page 2", "petite page 3"], max_chars=3000
    )
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


@ingest_document_suite.test()
def test_chunk_prompt_warns_against_recreating_the_document(  # bug #2b
) -> None:
    """Le prompt rappelle explicitement que le document est DÉJÀ une fiche en
    base — sans ce rappel l'extracteur en recrée parfois une (bug vu en live)."""
    chunk = Chunk(page_start=1, page_end=1, text="contenu")
    rendered = chunk.prompt("Fiche de réglage presse à balles BX-9", 4)
    assert "existe déjà dans la base" in rendered
    assert "ne crée PAS de fiche pour le document lui-même" in rendered


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
    assert (
        guess_title(cleaned, "repli") == "Fiche réglage sertisseuse SX-40 — Version 3"
    )


@ingest_document_suite.test()
def test_guess_title_skips_breadcrumb_and_export_metadata_lines() -> None:  # bug #2a
    """Bug vu en live : un bandeau de catégorie (« Machines <client> Fabrique »,
    invention ici : « Machines Atelier Fabrycom ») précédait le VRAI titre, et
    l'entité `document` était créée sous ce bandeau au lieu du titre. guess_title
    doit sauter le bandeau ET les métadonnées d'export (date de MAJ, créateur,
    valideur, « Version N » seule) pour trouver la vraie première ligne de titre."""
    pages = [
        "Machines Atelier Fabrycom\n"
        "Mis à jour le 10/01/2026\n"
        "Créateur : R. Cepre\n"
        "Valideur : L. Morel\n"
        "Version 2\n"
        "\n"
        "Fiche de réglage presse à balles BX-9\n"
        "\n"
        "Cette fiche décrit le réglage courant."
    ]
    assert guess_title(pages, "repli") == "Fiche de réglage presse à balles BX-9"


@ingest_document_suite.test()
def test_guess_title_skips_very_short_lines() -> None:
    assert (
        guess_title(["Atelier\n\nFiche de réglage presse à balles BX-9"], "repli")
        == "Fiche de réglage presse à balles BX-9"
    )


@ingest_document_suite.test()
def test_guess_title_keeps_short_lowercase_line_not_a_breadcrumb() -> None:
    """Une ligne courte contenant un mot-outil en minuscule (donc pas TOUT
    capitalisée) n'est pas un fil d'Ariane — mais reste écartée si < 12
    caractères (règle indépendante) ; ici elle passe les deux."""
    assert guess_title(["la presse à balles"], "repli") == "la presse à balles"


# ──────────────────── read_title (métadonnées PDF) ────────────────────
@ingest_document_suite.test()
def test_read_title_none_for_txt_md() -> None:
    assert read_title(FIXTURE) is None  # sx40_fiche.txt n'a pas de métadonnées PDF


@ingest_document_suite.test()
def test_read_title_reads_pdf_metadata(tmp: Annotated[Path, Use(tmp_path)]) -> None:
    pdf_writer = PdfWriter()
    pdf_writer.add_blank_page(width=200, height=200)
    pdf_writer.add_metadata({"/Title": "Fiche de réglage presse à balles BX-9"})
    p = tmp / "fiche.pdf"
    with p.open("wb") as f:
        pdf_writer.write(f)
    assert read_title(p) == "Fiche de réglage presse à balles BX-9"


@ingest_document_suite.test()
def test_read_title_ignores_generic_or_filename_title(
    tmp: Annotated[Path, Use(tmp_path)],
) -> None:
    for title, filename in (
        ("Untitled", "a.pdf"),
        ("Microsoft Word - fiche.docx", "b.pdf"),
        ("c", "c.pdf"),
        # Vu en live sur une facture exportée par un logiciel de gestion : /Title = « M ».
        ("M", "facture.pdf"),
    ):
        pdf_writer = PdfWriter()
        pdf_writer.add_blank_page(width=200, height=200)
        pdf_writer.add_metadata({"/Title": title})
        p = tmp / filename
        with p.open("wb") as f:
            pdf_writer.write(f)
        assert read_title(p) is None, title


# ──────────────────── is_document_duplicate / merge_document_duplicates ────────────────────
@ingest_document_suite.test()
def test_is_document_duplicate_catches_reworded_title() -> None:  # bug #2c
    title = "Fiche de réglage presse à balles BX-9"
    assert is_document_duplicate(title, title)
    assert is_document_duplicate("Fiche réglage presse à balles BX-9", title)


@ingest_document_suite.test()
def test_is_document_duplicate_spares_a_real_entity_named_like_a_title_substring() -> (
    None
):
    """Mesuré : `token_set_ratio` seul donne 100 pour un nom de machine
    simplement CONTENU dans le titre — `is_document_duplicate` ne doit PAS
    fusionner la vraie fiche machine dans le document."""
    title = "Fiche de réglage presse à balles BX-9"
    assert not is_document_duplicate("presse à balles BX-9", title)


@ingest_document_suite.test()
def test_is_document_duplicate_empty_inputs() -> None:
    assert not is_document_duplicate("", "un titre")
    assert not is_document_duplicate("un nom", "")


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
                id=eid,
                name=name,
                type=etype,
                project=PROJ,
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
                id=eid,
                name=name,
                type=etype,
                project=PROJ,
            )
    await link_described_in(driver, ["mors-sx40"], "fiche-sx40", 2, project=PROJ)
    await link_described_in(driver, ["mors-sx40"], "fiche-sx40", 3, project=PROJ)
    await link_described_in(
        driver, ["mors-sx40"], "fiche-sx40", 2, project=PROJ
    )  # rejoué

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


# ──────────────────── merge_document_duplicates (Neo4j, bug #2c) ────────────────────
@ingest_document_suite.test()
async def test_merge_document_duplicates_merges_matching_entity_and_keeps_relations(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Bug vu en live : l'extracteur crée parfois une fiche à part pour le
    document lui-même malgré la consigne du prompt (Chunk.prompt) — le doublon
    est fusionné DANS le VRAI document, ses relations le suivent. Une VRAIE
    fiche machine dont le nom est un sous-ensemble du titre n'est PAS touchée."""
    await _wipe(driver)
    title = "Fiche de réglage presse à balles BX-9"
    document_id = slugify(title)
    dup_id = "fiche-de-la-presse-bx-9"  # id distinct choisi par l'extracteur
    machine_id = "presse-a-balles-bx-9"  # VRAIE machine, à ne PAS fusionner
    async with driver.session() as session:
        for eid, name, etype in (
            (document_id, title, "document"),
            (dup_id, "Fiche réglage presse à balles BX-9", "document"),
            (machine_id, "presse à balles BX-9", "machine"),
            ("butee-bx9", "butée BX-9", "organe"),
        ):
            await session.run(
                "MERGE (e:GenEntity {id: $id, project: $project})"
                " SET e.name = $name, e.entity_type = $type",
                id=eid,
                name=name,
                type=etype,
                project=PROJ,
            )
        # Relation posée à tort vers le doublon au lieu du vrai document.
        await session.run(
            "MATCH (a:GenEntity {id: $a, project: $p}), (b:GenEntity {id: $b, project: $p})"
            " MERGE (a)-[:REL {rel_type: 'APPLIES_TO'}]->(b)",
            a="butee-bx9",
            b=dup_id,
            p=PROJ,
        )

    touched = {dup_id, machine_id}
    remaining = await merge_document_duplicates(
        driver,
        touched,
        document_id,
        title,
        project=PROJ,
    )
    assert remaining == {machine_id}, (
        "le doublon disparaît de touched, la vraie machine reste"
    )

    async with driver.session() as session:
        dup_still = await (
            await session.run(
                "MATCH (e:GenEntity {id: $id, project: $p}) RETURN e",
                id=dup_id,
                p=PROJ,
            )
        ).single()
        assert dup_still is None, (
            "le doublon a été supprimé (DETACH DELETE, merge_entity_into)"
        )

        rel = await (
            await session.run(
                "MATCH (:GenEntity {id: 'butee-bx9', project: $p})"
                "-[r:REL {rel_type: 'APPLIES_TO'}]->(:GenEntity {id: $doc, project: $p})"
                " RETURN count(r) AS n",
                p=PROJ,
                doc=document_id,
            )
        ).single()
        assert rel["n"] == 1, "la relation suit désormais le document"

        machine_still = await (
            await session.run(
                "MATCH (e:GenEntity {id: $id, project: $p}) RETURN e.entity_type AS t",
                id=machine_id,
                p=PROJ,
            )
        ).single()
        assert machine_still["t"] == "machine", "la vraie machine n'a pas été fusionnée"


@ingest_document_suite.test()
async def test_merge_document_duplicates_noop_when_nothing_matches(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    title = "Fiche de réglage presse à balles BX-9"
    document_id = slugify(title)
    async with driver.session() as session:
        for eid, name, etype in (
            (document_id, title, "document"),
            ("butee-bx9", "butée BX-9", "organe"),
        ):
            await session.run(
                "MERGE (e:GenEntity {id: $id, project: $project})"
                " SET e.name = $name, e.entity_type = $type",
                id=eid,
                name=name,
                type=etype,
                project=PROJ,
            )
    remaining = await merge_document_duplicates(
        driver,
        {"butee-bx9"},
        document_id,
        title,
        project=PROJ,
    )
    assert remaining == {"butee-bx9"}


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
    assert pages_mentioning(["Pression dapproche"], _SX40_PAGES) == [
        3
    ]  # tolère une coquille


@ingest_document_suite.test()
def test_pages_mentioning_uses_property_values_when_name_is_invented() -> None:
    # Nom forgé par le modèle, absent du texte ; sa valeur verbatim, elle, y est.
    assert pages_mentioning(["Réglage de course", "1 cran = 0,5 mm"], _SX40_PAGES) == [
        4
    ]


@ingest_document_suite.test()
def test_pages_mentioning_ignores_short_noise_and_returns_empty_when_absent() -> None:
    assert pages_mentioning(["à", "3", ""], _SX40_PAGES) == []
    assert pages_mentioning(["Mâchoire inférieure"], _SX40_PAGES) == []


@ingest_document_suite.test()
def test_entity_pages_prefers_name_over_loose_property_matches() -> None:
    # Vu en live : « à gauche du pupitre » (prop) matchait flou la page 1
    # (« les boutons du pupitre ») → Bouton START attribué pages 1-3 au lieu de 2.
    pages = {1: "Cette fiche couvre les boutons du pupitre.", **_SX40_PAGES}
    node = {
        "id": "bouton-start",
        "name": "Bouton START",
        "emplacement": "à gauche du pupitre",
        "role": "lance le cycle",
    }
    assert entity_pages(node, pages) == [2]


@ingest_document_suite.test()
def test_entity_pages_falls_back_to_properties_then_to_all_pages() -> None:
    node = {"id": "x", "name": "Réglage de course", "valeur": "1 cran = 0,5 mm"}
    assert entity_pages(node, _SX40_PAGES) == [4]
    ghost = {"id": "y", "name": "Mâchoire inférieure"}
    assert entity_pages(ghost, _SX40_PAGES) == [2, 3, 4]


# ──────────────── stream_ingest_document : streaming SSE (#import) ────────────────
# `run_extractors` est STUBBÉ (pas un TestModel) : ce qu'on vérifie ici est
# l'orchestration DE stream_ingest_document elle-même (ordre des events, traduction
# phase → « Bloc i/N… », propagation des cartes tool, event report final) — pas le
# comportement du pipeline d'extraction partagé, déjà couvert ailleurs.
_STUB_TOOL_CARD = {
    "kind": "tool",
    "tool": "fiche",
    "title": "Fiche",
    "subject": "Test",
    "field": "x",
    "added": "y",
    "entity_id": "stub-id",
    "relation": None,
}


async def _stub_run_extractors(*_args: object, **_kwargs: object):
    """Simule 2 passes (entités, relations) du pipeline partagé : une phase +
    une carte tool pour la première, une phase seule pour la seconde — assez
    pour vérifier l'ordre sans dépendre d'un vrai modèle."""
    yield ServerSentEvent(data="Felix met à jour la bible…", event="phase")
    yield ServerSentEvent(data=json.dumps(_STUB_TOOL_CARD), event="tool")
    yield ServerSentEvent(data="Felix relie les fiches…", event="phase")


def _make_touch_stub(entity_id: str):
    """Variante de `_stub_run_extractors` qui peuple aussi `chunk_deps.touched_ids`
    (#83) — `run_extractors` est appelé par `stream_ingest_document` en positionnel
    (agent, relation_agent, chronicle_agent, extract_prompt, chunk_prompt,
    message_history, chunk_deps, profile) : `args[6]` est `chunk_deps`. Nécessaire
    pour vérifier que `IngestReport.touched_ids`/la provenance PRODUCED reflètent
    de VRAIES entités touchées, sans dépendre d'un modèle réel."""

    async def _stub(*args: object, **_kwargs: object):
        args[6].touched_ids.add(entity_id)  # type: ignore[attr-defined]
        yield ServerSentEvent(data="Felix met à jour la bible…", event="phase")
        yield ServerSentEvent(data=json.dumps(_STUB_TOOL_CARD), event="tool")
        yield ServerSentEvent(data="Felix relie les fiches…", event="phase")

    return _stub


_STREAM_PROJ = "test-ingest-stream-v1"


async def _wipe_stream_proj(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n:GenEntity {project: $p}) DETACH DELETE n",
            p=_STREAM_PROJ,
        )


@ingest_document_suite.test()
async def test_stream_ingest_document_emits_phase_then_tool_then_report(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe_stream_proj(driver)
    try:
        with patch("felix.ingest.document.run_extractors", _stub_run_extractors):
            events = [
                ev
                async for ev in stream_ingest_document(
                    driver,
                    ["Page de test avec du contenu."],
                    profile=MAINTENANCE_PROFILE,
                    agent=MagicMock(),
                    relation_agent=MagicMock(),
                    chronicle_agent=MagicMock(),
                    project=_STREAM_PROJ,
                )
            ]
        kinds = [ev.event for ev in events]
        assert kinds == ["phase", "phase", "tool", "phase", "phase", "report"], kinds
        # Phase de lecture, puis les deux phases du bloc traduites (label + étape) —
        # « Felix met à jour la bible… »/« Felix relie les fiches… » (génériques,
        # pensées pour le chat) ne doivent JAMAIS fuiter telles quelles ici.
        assert events[0].data == "Lecture du document…"
        assert events[1].data == "Bloc 1/1 (page 1) : fiches…"
        assert events[3].data == "Bloc 1/1 (page 1) : liens…"
        assert events[4].data == "Vérification de la cohérence…"
        assert "Felix met à jour la bible" not in " ".join(e.data for e in events)
        # La carte tool est retransmise TELLE QUELLE (même carte que le chat).
        assert json.loads(events[2].data) == _STUB_TOOL_CARD
        # L'event report final porte un IngestReport valide et cohérent avec le stub.
        report = IngestReport.model_validate_json(events[-1].data)
        assert report.chunks == 1
        assert report.title == "Page de test avec du contenu."
    finally:
        await _wipe_stream_proj(driver)


@ingest_document_suite.test()
async def test_ingest_document_await_helper_matches_stream_final_report(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """`ingest_document` (CLI/e2e, #import) doit rester un simple raccourci
    « await » — son retour égale l'event `report` que `stream_ingest_document`
    aurait émis pour la MÊME entrée, comportement inchangé pour ses appelants."""
    pages = ["Une autre page de test, contenu différent."]
    await _wipe_stream_proj(driver)
    try:
        with patch("felix.ingest.document.run_extractors", _stub_run_extractors):
            events = [
                ev
                async for ev in stream_ingest_document(
                    driver,
                    pages,
                    profile=MAINTENANCE_PROFILE,
                    agent=MagicMock(),
                    relation_agent=MagicMock(),
                    chronicle_agent=MagicMock(),
                    project=_STREAM_PROJ,
                )
            ]
        expected = IngestReport.model_validate_json(events[-1].data)

        await _wipe_stream_proj(driver)
        with patch("felix.ingest.document.run_extractors", _stub_run_extractors):
            actual = await ingest_document(
                driver,
                pages,
                profile=MAINTENANCE_PROFILE,
                agent=MagicMock(),
                relation_agent=MagicMock(),
                chronicle_agent=MagicMock(),
                project=_STREAM_PROJ,
            )
        assert actual == expected
    finally:
        await _wipe_stream_proj(driver)


@ingest_document_suite.test()
async def test_ingest_document_raises_if_generator_never_reports(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Garde-fou : si le générateur ne produit jamais d'event `report` (bug
    interne), `ingest_document` échoue fort plutôt que de retourner `None`."""

    async def _no_report(*_args: object, **_kwargs: object):
        yield ServerSentEvent(data="Lecture du document…", event="phase")

    try:
        with patch("felix.ingest.document.stream_ingest_document", _no_report):
            raised = False
            try:
                await ingest_document(
                    driver,
                    ["page"],
                    profile=MAINTENANCE_PROFILE,
                    agent=MagicMock(),
                    relation_agent=MagicMock(),
                    chronicle_agent=MagicMock(),
                    project=_STREAM_PROJ,
                )
            except RuntimeError:
                raised = True
            assert raised
    finally:
        await _wipe_stream_proj(driver)


@ingest_document_suite.test()
async def test_stream_ingest_document_prefers_pdf_metadata_title(  # bug #2a
    driver: Annotated[AsyncDriver, Use(_driver)],
    tmp: Annotated[Path, Use(tmp_path)],
) -> None:
    """Titre en métadonnées PDF disponible → il gagne sur `guess_title`, même
    si la première ligne du texte est un bandeau de catégorie sans rapport
    (bug vu en live : le titre créé en base était ce bandeau, pas le vrai
    titre)."""
    meta_title = "Fiche de réglage presse à balles BX-9"
    pdf_writer = PdfWriter()
    pdf_writer.add_blank_page(width=400, height=400)
    pdf_writer.add_metadata({"/Title": meta_title})
    p = tmp / "fiche.pdf"
    with p.open("wb") as f:
        pdf_writer.write(f)

    await _wipe_stream_proj(driver)
    try:
        with (
            patch(
                "felix.ingest.document.read_pages",
                lambda _p: ["Machines Atelier Fabrycom"],
            ),
            patch("felix.ingest.document.run_extractors", _stub_run_extractors),
        ):
            events = [
                ev
                async for ev in stream_ingest_document(
                    driver,
                    p,
                    profile=MAINTENANCE_PROFILE,
                    agent=MagicMock(),
                    relation_agent=MagicMock(),
                    chronicle_agent=MagicMock(),
                    project=_STREAM_PROJ,
                )
            ]
        report = IngestReport.model_validate_json(events[-1].data)
        assert report.title == meta_title
    finally:
        await _wipe_stream_proj(driver)


# ──────────────── route POST /api/ingest/document : content-type SSE ────────────────


@ingest_document_suite.test()
async def test_ingest_route_streams_text_event_stream(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """La route ne doit plus rendre un JSON one-shot après 1 à 3 min de silence
    (#import) mais un flux `text/event-stream` — vérifié sur une app MINIMALE
    (SEUL le routeur ingest, pas felix.api.main : on ne veut pas du lifespan
    complet — collection Chroma incluse — pour un test de câblage de route)
    avec des agents `TestModel` (pydantic-ai, stub IN-PROCESS, cf.
    tests/unit/test_cost.py) : zéro appel LLM réel.

    `httpx.AsyncClient` + `ASGITransport` plutôt que `fastapi.testclient.TestClient` :
    ce dernier exécute la requête dans un thread à part (sa propre event loop),
    où le driver Neo4j de la fixture (créé sur LA loop du test) n'est pas
    valide — « Future attached to a different loop ». Le client async reste
    sur la même loop que le test."""
    proj = "test-ingest-route-v1"
    async with driver.session() as session:
        await session.run("MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=proj)

    stub_agent = Agent(TestModel())
    test_app = FastAPI()
    test_app.include_router(ingest_routes.router)
    test_app.dependency_overrides[api_deps.get_driver] = lambda: driver
    test_app.dependency_overrides[api_deps.get_atelier_agents] = lambda: {
        "maintenance": stub_agent
    }
    test_app.dependency_overrides[api_deps.get_relation_agents] = lambda: {
        "maintenance": stub_agent
    }
    test_app.dependency_overrides[api_deps.get_chronicle_agents] = lambda: {
        "maintenance": stub_agent
    }
    try:
        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/ingest/document",
                files={
                    "file": (
                        "note.txt",
                        b"Une fiche de test minimaliste.",
                        "text/plain",
                    )
                },
                data={"profile": "maintenance", "project": proj},
            )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.text
        assert "event: phase" in body
        assert "event: report" in body or "event: error" in body, body
    finally:
        async with driver.session() as session:
            await session.run(
                "MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=proj
            )


# ──────────────── provenance (#83) : PRODUCED depuis le message d'import ────────────────


@ingest_document_suite.test()
async def test_stream_ingest_document_report_exposes_touched_ids(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """`IngestReport.touched_ids` porte les entités RÉELLEMENT touchées par
    l'ingestion (hors document lui-même) — la route s'en sert pour poser la
    provenance PRODUCED (#83), même convention que `deps.touched_ids` côté chat."""
    await _wipe_stream_proj(driver)
    entity_id = "stub-touched-entity"
    async with driver.session() as session:
        await session.run(
            "MERGE (e:GenEntity {id: $id, project: $p})"
            " SET e.name = 'Stub touchée', e.entity_type = 'organe'",
            id=entity_id,
            p=_STREAM_PROJ,
        )
    try:
        with patch("felix.ingest.document.run_extractors", _make_touch_stub(entity_id)):
            events = [
                ev
                async for ev in stream_ingest_document(
                    driver,
                    ["Une page avec du contenu de test."],
                    profile=MAINTENANCE_PROFILE,
                    agent=MagicMock(),
                    relation_agent=MagicMock(),
                    chronicle_agent=MagicMock(),
                    project=_STREAM_PROJ,
                )
            ]
        report = IngestReport.model_validate_json(events[-1].data)
        assert report.touched_ids == [entity_id]
    finally:
        await _wipe_stream_proj(driver)


@ingest_document_suite.test()
async def test_ingest_route_links_produced_from_import_message(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """La route pose la provenance (#83) : le message « Import : <fichier> »
    PRODUCED les entités touchées — MÊME helper que le chat
    (felix.core.messages.link_produced), scoping fort par projet. Pipeline
    d'extraction stubbé (pas de LLM réel) mais touche une VRAIE entité en base,
    pour vérifier l'arête posée plutôt que juste sa plomberie."""
    proj = "test-ingest-provenance-v1"
    other_proj = "test-ingest-provenance-other-v1"
    # MÊME id d'entité dans les deux projets (#60) : vérifie que le scoping fort
    # de link_produced (MATCH ... project: $project) ne peut pas se tromper de nœud.
    entity_id = "stub-provenance-entity"
    async with driver.session() as session:
        await session.run("MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=proj)
        await session.run("MATCH (m:Message {project: $p}) DETACH DELETE m", p=proj)
        await session.run(
            "MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=other_proj
        )
        await session.run(
            "MERGE (e:GenEntity {id: $id, project: $p})"
            " SET e.name = 'Stub provenance', e.entity_type = 'organe'",
            id=entity_id,
            p=proj,
        )
        # Même id, projet DIFFÉRENT : ne doit recevoir AUCUNE arête (le message
        # importé appartient à `proj`, jamais à `other_proj`).
        await session.run(
            "MERGE (e:GenEntity {id: $id, project: $p})"
            " SET e.name = 'Stub autre projet', e.entity_type = 'organe'",
            id=entity_id,
            p=other_proj,
        )

    stub_agent = Agent(TestModel())
    test_app = FastAPI()
    test_app.include_router(ingest_routes.router)
    test_app.dependency_overrides[api_deps.get_driver] = lambda: driver
    test_app.dependency_overrides[api_deps.get_atelier_agents] = lambda: {
        "maintenance": stub_agent
    }
    test_app.dependency_overrides[api_deps.get_relation_agents] = lambda: {
        "maintenance": stub_agent
    }
    test_app.dependency_overrides[api_deps.get_chronicle_agents] = lambda: {
        "maintenance": stub_agent
    }
    try:
        with patch("felix.ingest.document.run_extractors", _make_touch_stub(entity_id)):
            transport = httpx.ASGITransport(app=test_app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/ingest/document",
                    files={
                        "file": (
                            "note.txt",
                            b"Une fiche de test minimaliste.",
                            "text/plain",
                        )
                    },
                    data={"profile": "maintenance", "project": proj},
                )
        assert response.status_code == 200
        assert "event: report" in response.text, response.text

        async with driver.session() as session:
            result = await session.run(
                "MATCH (m:Message {project: $p, role: 'user'})"
                "-[:PRODUCED]->(e:GenEntity {id: $id, project: $p})"
                " RETURN m.body AS body",
                p=proj,
                id=entity_id,
            )
            record = await result.single()
            assert record is not None, "aucune arête PRODUCED posée"
            assert record["body"] == "Import : note.txt"

            # Scoping fort (#60) : aucune arête ne fuit vers le nœud de MÊME id
            # dans l'AUTRE projet.
            leak = await (
                await session.run(
                    "MATCH (:Message)-[:PRODUCED]->(e:GenEntity {id: $id, project: $p})"
                    " RETURN count(e) AS n",
                    p=other_proj,
                    id=entity_id,
                )
            ).single()
            assert leak["n"] == 0
    finally:
        async with driver.session() as session:
            await session.run(
                "MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=proj
            )
            await session.run("MATCH (m:Message {project: $p}) DETACH DELETE m", p=proj)
            await session.run(
                "MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=other_proj
            )


@ingest_document_suite.test()
def test_guess_title_skips_lines_starting_with_a_number() -> None:
    # Vu en live sur une facture : l'adresse du chantier prise pour le titre.
    page = "12, rue des Presses\n26000 VALENCE\nFacture N° BX-0042 — presse à balles"
    assert guess_title([page], "fallback") == "Facture N° BX-0042 — presse à balles"


@ingest_document_suite.test()
def test_guess_title_skips_short_place_and_date_lines() -> None:
    # « VALENCE, le 03/02/2026 » : lieu + date d'un courrier/facture, pas un titre.
    page = "VALENCE, le 03/02/2026\nFacture N° BX-0042 — presse à balles"
    assert guess_title([page], "fallback") == "Facture N° BX-0042 — presse à balles"
