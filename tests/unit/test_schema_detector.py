"""Détecteur déterministe de propositions de schéma (Étape 5) — helpers PURS
(verb_head, cluster_verbs, pair_near_duplicate_types) + un test Neo4j de bout
en bout sur un graphe construit à la main.

Univers de TEST : presse à balles BX-9 (cf. [[feedback_prompt_test_leakage]]).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from protest import ProTestSuite, Use, fixture

from felix.core.profile import EMERGENT_SEED_PROFILE
from felix.core.schema_changes import MergeTypes, PromoteVerbs
from felix.core.schema_detector import (
    cluster_verbs,
    detect_proposals,
    pair_near_duplicate_types,
    verb_head,
)
from felix.graph.driver import get_driver, setup_constraints
from felix.ingest.resolver import slugify

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

schema_detector_suite = ProTestSuite("SchemaDetector")

PROJ = "test-schema-detector"


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


async def _seed_entity(driver: AsyncDriver, entity_id: str, name: str, etype: str) -> None:
    async with driver.session() as session:
        await session.run(
            "MERGE (e:GenEntity {id: $id, project: $project})"
            " SET e.name = $name, e.entity_type = $type",
            id=entity_id, name=name, type=etype, project=PROJ,
        )


async def _seed_narrative(driver: AsyncDriver, from_id: str, to_id: str, verbe: str) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (a:GenEntity {id: $a, project: $p}), (b:GenEntity {id: $b, project: $p})"
            " MERGE (a)-[r:REL {rel_type: 'LIE_A', verbe_slug: $vs}]->(b)"
            " SET r.verbe = $verbe",
            a=from_id, b=to_id, p=PROJ, vs=slugify(verbe), verbe=verbe,
        )


# ──────────────────── verb_head (pur) ────────────────────

@schema_detector_suite.test()
def test_verb_head_plain_verb() -> None:
    assert verb_head("règle") == "regle"


@schema_detector_suite.test()
def test_verb_head_strips_leading_function_words() -> None:
    assert verb_head("est réglé par") == "regle"
    assert verb_head("qui pilote") == "pilote"


@schema_detector_suite.test()
def test_verb_head_strips_trailing_s() -> None:
    assert verb_head("règles") == "regle"


@schema_detector_suite.test()
def test_verb_head_pure_function_words_is_empty() -> None:
    assert verb_head("est pour") == ""


@schema_detector_suite.test()
def test_verb_head_case_and_accent_insensitive() -> None:
    assert verb_head("RÈGLE") == verb_head("regle")


# ──────────────────── cluster_verbs (pur) ────────────────────

@schema_detector_suite.test()
def test_cluster_verbs_groups_by_head_above_threshold() -> None:
    edges = [{"verbe": "règle"}, {"verbe": "est réglé par"}, {"verbe": "pilote"}]
    clusters = cluster_verbs(edges, min_count=2)
    assert set(clusters) == {"regle"}
    assert len(clusters["regle"]) == 2


@schema_detector_suite.test()
def test_cluster_verbs_below_threshold_excluded() -> None:
    edges = [{"verbe": "règle"}]
    assert cluster_verbs(edges, min_count=2) == {}


@schema_detector_suite.test()
def test_cluster_verbs_ignores_empty_head() -> None:
    edges = [{"verbe": "est pour"}, {"verbe": "est pour"}]
    assert cluster_verbs(edges, min_count=2) == {}


# ──────────────────── pair_near_duplicate_types (pur) ────────────────────

@schema_detector_suite.test()
def test_pair_near_duplicate_types_same_singular() -> None:
    merges = pair_near_duplicate_types({"organe": 5, "organes": 1})
    assert len(merges) == 1
    assert merges[0].sources == ["organes"]
    assert merges[0].target == "organe"


@schema_detector_suite.test()
def test_pair_near_duplicate_types_fuzzy_match() -> None:
    """« reservoir »/« reservoire » : pas le même singulier normalisé (aucun ne
    finit en s), mais une ressemblance floue ≥ 85 (une coquille)."""
    merges = pair_near_duplicate_types({"reservoir": 4, "reservoire": 1})
    assert any(m.sources == ["reservoire"] and m.target == "reservoir" for m in merges)


@schema_detector_suite.test()
def test_pair_near_duplicate_types_no_match_stays_separate() -> None:
    assert pair_near_duplicate_types({"organe": 3, "commande": 2}) == []


@schema_detector_suite.test()
def test_pair_near_duplicate_types_rarer_source_more_frequent_target() -> None:
    merges = pair_near_duplicate_types({"piston": 1, "pistons": 9})
    assert merges == [MergeTypes(sources=["piston"], target="pistons")]


# ──────────────────── detect_proposals (Neo4j, bout en bout) ────────────────────

@schema_detector_suite.test()
async def test_detect_proposals_verb_cluster(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    await _seed_entity(driver, "verin", "Vérin", "organe")
    await _seed_entity(driver, "trappe", "Trappe", "organe")
    await _seed_entity(driver, "levier", "Levier", "commande")
    await _seed_entity(driver, "pression", "Pression hydraulique", "parametre")
    # Deux arêtes de MÊME tête de verbe ("règle") sur deux paires différentes —
    # atteint min_count=2 et fait apparaître les DEUX paires observées.
    await _seed_narrative(driver, "levier", "verin", "règle")
    await _seed_narrative(driver, "levier", "pression", "règle")

    proposals = await detect_proposals(
        driver, project=PROJ, profile=EMERGENT_SEED_PROFILE, min_count=2
    )
    promote = [p for p in proposals if isinstance(p.change, PromoteVerbs)]
    assert len(promote) == 1
    assert promote[0].change.rel_type == "REGLE"
    assert sorted(promote[0].report.observed_pairs) == [
        ("commande", "organe"), ("commande", "parametre"),
    ]


@schema_detector_suite.test()
async def test_detect_proposals_below_min_count_yields_no_verb_proposal(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    await _seed_entity(driver, "verin", "Vérin", "organe")
    await _seed_entity(driver, "trappe", "Trappe", "organe")
    await _seed_narrative(driver, "verin", "trappe", "règle")

    proposals = await detect_proposals(
        driver, project=PROJ, profile=EMERGENT_SEED_PROFILE, min_count=2
    )
    assert not [p for p in proposals if isinstance(p.change, PromoteVerbs)]


@schema_detector_suite.test()
async def test_detect_proposals_type_near_duplicate(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    await _seed_entity(driver, "verin1", "Vérin 1", "verin")
    await _seed_entity(driver, "verin2", "Vérin 2", "verin")
    await _seed_entity(driver, "verin3", "Vérin 3", "verin")
    await _seed_entity(driver, "verinbis", "Vérin bis", "verins")

    proposals = await detect_proposals(
        driver, project=PROJ, profile=EMERGENT_SEED_PROFILE, min_count=2
    )
    merges = [p for p in proposals if isinstance(p.change, MergeTypes)]
    assert any(m.change.sources == ["verins"] and m.change.target == "verin" for m in merges)


@schema_detector_suite.test()
async def test_detect_proposals_excludes_document_and_evenement_types(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    await _seed_entity(driver, "doc1", "Fiche 1", "document")
    await _seed_entity(driver, "doc2", "Fiche 2", "document")
    await _seed_entity(driver, "ev1", "Événement 1", "evenement")

    proposals = await detect_proposals(
        driver, project=PROJ, profile=EMERGENT_SEED_PROFILE, min_count=2
    )
    assert not [p for p in proposals if isinstance(p.change, MergeTypes)]


@schema_detector_suite.test()
async def test_detect_proposals_etancheite_projet(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Un cluster du projet B ne doit jamais apparaître dans les propositions du
    projet A (#60 : la même garantie que partout ailleurs)."""
    await _wipe(driver)
    proj_b = PROJ + "-b"
    async with driver.session() as session:
        await session.run(
            "MERGE (a:GenEntity {id: 'x', project: $p}) SET a.name='X', a.entity_type='organe'",
            p=proj_b,
        )
        await session.run(
            "MERGE (b:GenEntity {id: 'y', project: $p}) SET b.name='Y', b.entity_type='organe'",
            p=proj_b,
        )
        await session.run(
            "MATCH (a:GenEntity {id:'x', project:$p}), (b:GenEntity {id:'y', project:$p})"
            " MERGE (a)-[r:REL {rel_type:'LIE_A', verbe_slug:$vs}]->(b)"
            " SET r.verbe=$verbe",
            p=proj_b, vs=slugify("regule"), verbe="régule",
        )
        await session.run(
            "MATCH (a:GenEntity {id:'x', project:$p}), (b:GenEntity {id:'y', project:$p})"
            " MERGE (a)-[r:REL {rel_type:'LIE_A', verbe_slug:'regule2'}]->(b)"
            " SET r.verbe='régule encore'",
            p=proj_b,
        )
        try:
            proposals = await detect_proposals(
                driver, project=PROJ, profile=EMERGENT_SEED_PROFILE, min_count=2
            )
            assert not [p for p in proposals if isinstance(p.change, PromoteVerbs)]
        finally:
            await session.run("MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=proj_b)
