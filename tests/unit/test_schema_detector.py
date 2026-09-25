"""Détecteur déterministe de propositions de schéma (Étape 5) — helpers PURS
(verb_head, cluster_verbs, pair_near_duplicate_types) + un test Neo4j de bout
en bout sur un graphe construit à la main.

Univers de TEST : presse à balles BX-9 (cf. [[feedback_prompt_test_leakage]]).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from protest import ProTestSuite, Use, fixture

from felix.core.profile import EMERGENT_SEED_PROFILE
from felix.core.profile_store import save_rejected_change
from felix.core.schema_changes import MergeTypes, PromoteVerbs
from felix.core.schema_detector import (
    cluster_verbs,
    content_tokens,
    detect_proposals,
    pair_near_duplicate_types,
    suggest_rel_type,
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
            "MATCH (n:GenEntity {project: $p}) DETACH DELETE n",
            p=PROJ,
        )


async def _wipe_profile(driver: AsyncDriver) -> None:
    """Le méta-nœud :ProjectProfile (refus, cf. Étape 8) — un espace à part de
    :GenEntity, nettoyé séparément pour ne pas polluer les tests qui refusent
    des propositions sur PROJ."""
    async with driver.session() as session:
        await session.run(
            "MATCH (p:ProjectProfile {project: $p}) DETACH DELETE p",
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
        await _wipe_profile(driver)
        await driver.close()


async def _seed_entity(
    driver: AsyncDriver, entity_id: str, name: str, etype: str
) -> None:
    async with driver.session() as session:
        await session.run(
            "MERGE (e:GenEntity {id: $id, project: $project})"
            " SET e.name = $name, e.entity_type = $type",
            id=entity_id,
            name=name,
            type=etype,
            project=PROJ,
        )


async def _seed_narrative(
    driver: AsyncDriver, from_id: str, to_id: str, verbe: str
) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (a:GenEntity {id: $a, project: $p}), (b:GenEntity {id: $b, project: $p})"
            " MERGE (a)-[r:REL {rel_type: 'LIE_A', verbe_slug: $vs}]->(b)"
            " SET r.verbe = $verbe",
            a=from_id,
            b=to_id,
            p=PROJ,
            vs=slugify(verbe),
            verbe=verbe,
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


# ──────────────────── stoplist étendu (bug live 2026-09-24 : cluster « UNE ») ────────────────────
# Vu en direct par l'utilisateur : « est UNE évolution du slogan pour » se
# voyait promu en rel_type « UNE » — l'article n'était pas dans le stoplist,
# qui ne retirait que « est ».


@schema_detector_suite.test()
def test_verb_head_strips_indefinite_article() -> None:
    assert verb_head("est une évolution du slogan pour") == "evolution"


@schema_detector_suite.test()
def test_verb_head_strips_que() -> None:
    assert verb_head("signale que la") == "signale"


@schema_detector_suite.test()
def test_verb_head_strips_locative_preposition() -> None:
    assert verb_head("est situé à gauche du") == "situe"


@schema_detector_suite.test()
def test_verb_head_unifies_infinitive_and_present_tense() -> None:
    """« basculer »/« bascule » retombent sur la même tête — même cluster."""
    assert verb_head("permet de basculer vers") == verb_head("bascule entre")


@schema_detector_suite.test()
def test_content_tokens_strips_extended_stopwords() -> None:
    assert content_tokens("est une évolution du slogan pour") == ["evolution", "slogan"]


# ──────────────────── suggest_rel_type (nom suggéré, distinct de la clé de cluster) ────────────────────


@schema_detector_suite.test()
def test_suggest_rel_type_evolution_slogan() -> None:
    assert suggest_rel_type("est une évolution du slogan pour") == "EVOLUTION"


@schema_detector_suite.test()
def test_suggest_rel_type_signale() -> None:
    assert suggest_rel_type("signale que la") == "SIGNALE"


@schema_detector_suite.test()
def test_suggest_rel_type_situe() -> None:
    assert suggest_rel_type("est situé à gauche du") == "SITUE"


@schema_detector_suite.test()
def test_suggest_rel_type_bascule_same_for_both_phrasings() -> None:
    assert suggest_rel_type("permet de basculer vers") == "BASCULE"
    assert suggest_rel_type("bascule entre") == "BASCULE"


@schema_detector_suite.test()
def test_suggest_rel_type_short_head_gets_second_token() -> None:
    """Premier token < 4 caractères (« vu ») : peu lisible seul, on complète
    avec le second token substantiel."""
    assert suggest_rel_type("vu dans le rapport") == "VU_RAPPORT"


@schema_detector_suite.test()
def test_suggest_rel_type_empty_verb_is_empty() -> None:
    assert suggest_rel_type("est pour") == ""


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


@schema_detector_suite.test()
def test_cluster_verbs_groups_infinitive_and_present_tense_together() -> None:
    """« permet de basculer vers » et « bascule entre » : même verbe, deux
    formes — un seul cluster (pas deux clusters de taille 1 sous le seuil)."""
    edges = [{"verbe": "permet de basculer vers"}, {"verbe": "bascule entre"}]
    clusters = cluster_verbs(edges, min_count=2)
    assert set(clusters) == {"bascule"}
    assert len(clusters["bascule"]) == 2


# ──────────────────── cluster_verbs : têtes conjonction/subordonnant (#81) ────────────────────
# Vu en direct par l'utilisateur : « sinon … » (repli conditionnel d'une
# phrase, pas un lien du domaine) promu en cluster « SINON ». « sinon » n'est
# pas un mot de fonction générique (au sens du stoplist qui retire des mots
# EN TÊTE d'un verbe réel) — c'est retiré APRÈS clustering, cf. schema_detector.


@schema_detector_suite.test()
def test_cluster_verbs_excludes_conjunction_head_sinon() -> None:
    edges = [{"verbe": "sinon on bascule"}, {"verbe": "sinon rien ne se passe"}]
    assert cluster_verbs(edges, min_count=2) == {}


@schema_detector_suite.test()
def test_cluster_verbs_excludes_conjunction_head_mais_puis() -> None:
    """« mais »/« puis » perdent leur « s » final via _light_suffix_strip
    (→ « mai »/« pui ») — le frozenset des conjonctions doit matcher la tête
    RÉELLEMENT produite par verb_head, pas l'orthographe brute."""
    edges_mais = [{"verbe": "mais rien ne change"}, {"verbe": "mais tout bascule"}]
    assert cluster_verbs(edges_mais, min_count=2) == {}
    edges_puis = [{"verbe": "puis il part"}, {"verbe": "puis elle revient"}]
    assert cluster_verbs(edges_puis, min_count=2) == {}


@schema_detector_suite.test()
def test_cluster_verbs_excludes_conjunction_head_elided_lorsqu() -> None:
    """Apostrophe TYPOGRAPHIQUE (U+2019, copié-collé Word/Docs — pas l'apostrophe
    droite ASCII reconnue par _normalize) : « lorsqu » + « il » élidés se
    scindent en deux tokens — la tête retombe pile sur la conjonction."""
    curly_apostrophe = chr(
        0x2019
    )  # U+2019 — construit à part, RUF001 le flague en littéral
    edges = [
        {"verbe": f"lorsqu{curly_apostrophe}il bascule"},
        {"verbe": f"lorsqu{curly_apostrophe}elle bascule"},
    ]
    assert cluster_verbs(edges, min_count=2) == {}


@schema_detector_suite.test()
def test_cluster_verbs_real_verb_not_excluded_by_conjunction_filter() -> None:
    """Garde-fou : le filtre ne doit pas mordre sur un vrai verbe — aucune tête
    de la liste des conjonctions n'est un préfixe/radical de « règle »."""
    edges = [{"verbe": "règle"}, {"verbe": "est réglé par"}]
    clusters = cluster_verbs(edges, min_count=2)
    assert set(clusters) == {"regle"}
    assert len(clusters["regle"]) == 2


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
        ("commande", "organe"),
        ("commande", "parametre"),
    ]


@schema_detector_suite.test()
async def test_detect_proposals_verb_cluster_payload_for_humans(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Étape 5bis (2026-09-24, après le retour « je ne comprends rien ») : le
    panneau a besoin d'occurrences/phrases/exemples/pairs_readable pour ne
    plus montrer du jargon (« UNE », des chips non expliqués)."""
    await _wipe(driver)
    await _seed_entity(driver, "verin", "Vérin", "organe")
    await _seed_entity(driver, "trappe", "Trappe", "organe")
    await _seed_entity(driver, "levier", "Levier", "commande")
    await _seed_narrative(driver, "levier", "verin", "règle")
    await _seed_narrative(driver, "levier", "trappe", "règle")

    proposals = await detect_proposals(
        driver, project=PROJ, profile=EMERGENT_SEED_PROFILE, min_count=2
    )
    promote = [p for p in proposals if isinstance(p.change, PromoteVerbs)]
    assert len(promote) == 1
    proposal = promote[0]
    assert proposal.occurrences == 2
    assert proposal.phrases == ["règle"]
    assert len(proposal.examples) == 2
    assert {e["from"] for e in proposal.examples} == {"Levier"}
    assert {e["to"] for e in proposal.examples} == {"Vérin", "Trappe"}
    assert proposal.pairs_readable == "commande → organe"


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
async def test_detect_proposals_excludes_document_edges_from_verb_clusters(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """#81 : la moitié des propositions vues en direct était du bruit —
    CONCERNE/COUVRE, des LIE_A du nœud `document` (méta, posé par
    l'ingestion) vers tout le graphe, jamais un lien du domaine. Un cluster
    document→X ne doit produire AUCUNE proposition, même au-dessus de
    min_count."""
    await _wipe(driver)
    await _seed_entity(driver, "doc1", "Fiche 1", "document")
    await _seed_entity(driver, "verin", "Vérin", "organe")
    await _seed_entity(driver, "trappe", "Trappe", "organe")
    await _seed_narrative(driver, "doc1", "verin", "concerne")
    await _seed_narrative(driver, "doc1", "trappe", "concerne")

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
    assert any(
        m.change.sources == ["verins"] and m.change.target == "verin" for m in merges
    )


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
            p=proj_b,
            vs=slugify("regule"),
            verbe="régule",
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
            await session.run(
                "MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=proj_b
            )


# ──────────────────── refus persistés (file de validation, Étape 8) ────────────────────


@schema_detector_suite.test()
async def test_detect_proposals_skips_rejected_verb_cluster(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Un refus porte sur l'ENSEMBLE SOURCE (verbe_slugs), pas sur le nom cible
    proposé — refuser « règle → AUTRE_NOM » doit aussi taire « règle → REGLE »
    (même cluster, seul le nom change)."""
    await _wipe(driver)
    await _wipe_profile(driver)
    await _seed_entity(driver, "verin", "Vérin", "organe")
    await _seed_entity(driver, "trappe", "Trappe", "organe")
    await _seed_entity(driver, "levier", "Levier", "commande")
    await _seed_narrative(driver, "levier", "verin", "règle")
    await _seed_narrative(driver, "levier", "trappe", "règle")
    await save_rejected_change(
        driver,
        PromoteVerbs(verbe_slugs=["regle"], rel_type="AUTRE_NOM"),
        project=PROJ,
    )
    try:
        proposals = await detect_proposals(
            driver, project=PROJ, profile=EMERGENT_SEED_PROFILE, min_count=2
        )
        assert not [p for p in proposals if isinstance(p.change, PromoteVerbs)]
    finally:
        await _wipe_profile(driver)


@schema_detector_suite.test()
async def test_detect_proposals_does_not_skip_unrelated_verb_cluster(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Un refus sur un AUTRE cluster (verbe_slugs différents) ne doit rien taire."""
    await _wipe(driver)
    await _wipe_profile(driver)
    await _seed_entity(driver, "verin", "Vérin", "organe")
    await _seed_entity(driver, "trappe", "Trappe", "organe")
    await _seed_entity(driver, "levier", "Levier", "commande")
    await _seed_narrative(driver, "levier", "verin", "règle")
    await _seed_narrative(driver, "levier", "trappe", "règle")
    await save_rejected_change(
        driver,
        PromoteVerbs(verbe_slugs=["pilote"], rel_type="CONTROLS"),
        project=PROJ,
    )
    try:
        proposals = await detect_proposals(
            driver, project=PROJ, profile=EMERGENT_SEED_PROFILE, min_count=2
        )
        promote = [p for p in proposals if isinstance(p.change, PromoteVerbs)]
        assert len(promote) == 1
    finally:
        await _wipe_profile(driver)


@schema_detector_suite.test()
async def test_detect_proposals_skips_rejected_type_merge(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Même règle pour MergeTypes : le refus porte sur l'ensemble `sources`."""
    await _wipe(driver)
    await _wipe_profile(driver)
    await _seed_entity(driver, "verin1", "Vérin 1", "verin")
    await _seed_entity(driver, "verin2", "Vérin 2", "verin")
    await _seed_entity(driver, "verinbis", "Vérin bis", "verins")
    await save_rejected_change(
        driver,
        MergeTypes(sources=["verins"], target="verinou"),
        project=PROJ,
    )
    try:
        proposals = await detect_proposals(
            driver, project=PROJ, profile=EMERGENT_SEED_PROFILE, min_count=2
        )
        merges = [p for p in proposals if isinstance(p.change, MergeTypes)]
        assert not [m for m in merges if m.change.sources == ["verins"]]
    finally:
        await _wipe_profile(driver)
