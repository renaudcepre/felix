"""Migration du passé — appliquer un changement de schéma validé au graphe existant.

Moteur pur (pas de détecteur, pas d'UI, pas de persistance de profil, aucun
appel LLM) : ``PromoteVerbs`` fait entrer des paraphrases narratives (LIE_A +
verbe) dans le vocabulaire structurel, ``MergeTypes`` fond un ou plusieurs
entity_type dans un seul. ``preview`` calcule le même rapport SANS écrire —
un seul chemin de calcul pour les deux modes.

Univers de TEST : presse à balles BX-9 (vérin, trappe, levier, pression
hydraulique) — frais, absent de tous les prompts (anti-leakage, cf.
[[feedback_prompt_test_leakage]]).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from protest import ProTestSuite, Use, fixture, raises

from felix.core.schema_changes import MergeTypes, PromoteVerbs, apply_schema_change
from felix.graph.driver import get_driver, setup_constraints
from felix.ingest.resolver import slugify

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

schema_changes_suite = ProTestSuite("SchemaChanges")

PROJ = "test-schema-changes"
PROJ_B = PROJ + "-b"


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n:GenEntity) WHERE n.project IN [$p, $p2] DETACH DELETE n",
            p=PROJ,
            p2=PROJ_B,
        )


@fixture(max_concurrency=1)
async def _schema_driver() -> AsyncGenerator[AsyncDriver]:
    driver = get_driver()
    await setup_constraints(driver)
    try:
        yield driver
    finally:
        await _wipe(driver)
        await driver.close()


async def _seed_entity(
    driver: AsyncDriver, entity_id: str, name: str, etype: str, *, proj: str = PROJ
) -> None:
    async with driver.session() as session:
        await session.run(
            "MERGE (e:GenEntity {id: $id, project: $project})"
            " SET e.name = $name, e.entity_type = $type",
            id=entity_id,
            name=name,
            type=etype,
            project=proj,
        )


async def _seed_narrative(
    driver: AsyncDriver,
    from_id: str,
    to_id: str,
    verbe: str,
    *,
    proj: str = PROJ,
    props: dict | None = None,
) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (a:GenEntity {id: $a, project: $p}), (b:GenEntity {id: $b, project: $p})"
            " MERGE (a)-[r:REL {rel_type: 'LIE_A', verbe_slug: $vs}]->(b)"
            " SET r.verbe = $verbe, r += $props",
            a=from_id,
            b=to_id,
            p=proj,
            vs=slugify(verbe),
            verbe=verbe,
            props=props or {},
        )


async def _seed_typed(
    driver: AsyncDriver,
    from_id: str,
    to_id: str,
    rel_type: str,
    *,
    proj: str = PROJ,
    props: dict | None = None,
) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (a:GenEntity {id: $a, project: $p}), (b:GenEntity {id: $b, project: $p})"
            " MERGE (a)-[r:REL {rel_type: $t}]->(b) SET r += $props",
            a=from_id,
            b=to_id,
            p=proj,
            t=rel_type,
            props=props or {},
        )


async def _typed_edge(
    driver: AsyncDriver, from_id: str, to_id: str, rel_type: str, *, proj: str = PROJ
) -> dict | None:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (a:GenEntity {id: $a, project: $p})-[r:REL {rel_type: $t}]->"
            "(b:GenEntity {id: $b, project: $p}) RETURN properties(r) AS props",
            a=from_id,
            b=to_id,
            p=proj,
            t=rel_type,
        )
        record = await result.single()
        return dict(record["props"]) if record else None


async def _narrative_count(driver: AsyncDriver, *, proj: str = PROJ) -> int:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (:GenEntity {project: $p})-[r:REL {rel_type: 'LIE_A'}]->"
            "(:GenEntity {project: $p}) RETURN count(r) AS n",
            p=proj,
        )
        record = await result.single()
        return record["n"] if record else 0


async def _entity_type(
    driver: AsyncDriver, entity_id: str, *, proj: str = PROJ
) -> str | None:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (e:GenEntity {id: $id, project: $p}) RETURN e.entity_type AS t",
            id=entity_id,
            p=proj,
        )
        record = await result.single()
        return record["t"] if record else None


async def _seed_bx9(driver: AsyncDriver, *, proj: str = PROJ) -> None:
    """Vérin/trappe (organe), levier (commande), pression hydraulique (parametre)."""
    await _seed_entity(driver, "verin", "Vérin", "organe", proj=proj)
    await _seed_entity(driver, "trappe", "Trappe", "organe", proj=proj)
    await _seed_entity(driver, "levier", "Levier", "commande", proj=proj)
    await _seed_entity(
        driver, "pression", "Pression hydraulique", "parametre", proj=proj
    )


# ──────────────────── PromoteVerbs : cas nominaux ────────────────────


@schema_changes_suite.test()
async def test_promote_deux_paraphrases_paires_differentes(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    """Deux verbes promus sur deux paires DIFFÉRENTES → deux arêtes typées, 0 collapse."""
    await _wipe(driver)
    await _seed_bx9(driver)
    await _seed_narrative(driver, "verin", "trappe", "règle")
    await _seed_narrative(driver, "levier", "pression", "pilote")

    change = PromoteVerbs(
        verbe_slugs=[slugify("règle"), slugify("pilote")], rel_type="CONTROLS"
    )
    report = await apply_schema_change(driver, change, project=PROJ)

    assert report.edges_converted == 2
    assert report.edges_collapsed == 0
    assert await _narrative_count(driver) == 0

    props1 = await _typed_edge(driver, "verin", "trappe", "CONTROLS")
    props2 = await _typed_edge(driver, "levier", "pression", "CONTROLS")
    assert props1 is not None and props1["verbe_origine"] == ["règle"]
    assert props2 is not None and props2["verbe_origine"] == ["pilote"]
    assert "verbe" not in props1 and "verbe_slug" not in props1

    assert sorted(report.observed_pairs) == [
        ("commande", "parametre"),
        ("organe", "organe"),
    ]
    assert report.samples and len(report.samples) <= 5
    assert "règle" in report.samples[0] or "pilote" in report.samples[0]


@schema_changes_suite.test()
async def test_promote_deux_paraphrases_meme_paire_collapse(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    """« règle » et « pilote » sur LA MÊME paire → UNE arête typée, verbe_origine = les deux."""
    await _wipe(driver)
    await _seed_bx9(driver)
    await _seed_narrative(driver, "verin", "trappe", "règle")
    await _seed_narrative(driver, "verin", "trappe", "pilote")

    change = PromoteVerbs(
        verbe_slugs=[slugify("règle"), slugify("pilote")], rel_type="CONTROLS"
    )
    report = await apply_schema_change(driver, change, project=PROJ)

    assert report.edges_converted == 2
    assert report.edges_collapsed == 1
    assert await _narrative_count(driver) == 0

    props = await _typed_edge(driver, "verin", "trappe", "CONTROLS")
    assert props is not None
    assert sorted(props["verbe_origine"]) == ["pilote", "règle"]


@schema_changes_suite.test()
async def test_promote_collapse_dans_arete_preexistante(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    """Promotion qui retombe sur une arête CONTROLS déjà posée : MERGE dans
    l'existante, propriétés conflictuelles gagnées par l'EXISTANT, nouvelles ajoutées."""
    await _wipe(driver)
    await _seed_bx9(driver)
    await _seed_typed(driver, "verin", "trappe", "CONTROLS", props={"note": "visuel"})
    await _seed_narrative(
        driver,
        "verin",
        "trappe",
        "règle",
        props={"note": "ancien", "fiabilite": "haute"},
    )

    change = PromoteVerbs(verbe_slugs=[slugify("règle")], rel_type="CONTROLS")
    report = await apply_schema_change(driver, change, project=PROJ)

    assert report.edges_converted == 1
    assert report.edges_collapsed == 1

    props = await _typed_edge(driver, "verin", "trappe", "CONTROLS")
    assert props is not None
    assert props["note"] == "visuel", "l'existant gagne sur conflit"
    assert props["fiabilite"] == "haute", "prop nouvelle ajoutée"
    assert props["verbe_origine"] == ["règle"]


@schema_changes_suite.test()
async def test_promote_reverse_inverse_le_sens(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    """Verbe passif (« est réglé par ») + reverse=True → arête typée dans le sens INVERSE."""
    await _wipe(driver)
    await _seed_bx9(driver)
    await _seed_narrative(driver, "trappe", "levier", "est réglé par")

    change = PromoteVerbs(
        verbe_slugs=[slugify("est réglé par")], rel_type="CONTROLS", reverse=True
    )
    report = await apply_schema_change(driver, change, project=PROJ)

    assert report.edges_converted == 1
    assert await _typed_edge(driver, "levier", "trappe", "CONTROLS") is not None
    assert await _typed_edge(driver, "trappe", "levier", "CONTROLS") is None
    assert report.observed_pairs == [("commande", "organe")]


@schema_changes_suite.test()
async def test_observed_pairs_dedupe(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    """Deux arêtes distinctes de même paire de TYPES → observed_pairs dédupliqué."""
    await _wipe(driver)
    await _seed_entity(driver, "verin", "Vérin", "organe")
    await _seed_entity(driver, "trappe", "Trappe", "organe")
    await _seed_entity(driver, "coffre", "Coffre", "organe")
    await _seed_entity(driver, "porte", "Porte", "organe")
    await _seed_narrative(driver, "verin", "trappe", "règle")
    await _seed_narrative(driver, "coffre", "porte", "pilote")

    change = PromoteVerbs(
        verbe_slugs=[slugify("règle"), slugify("pilote")], rel_type="CONTROLS"
    )
    report = await apply_schema_change(driver, change, project=PROJ)

    assert report.edges_collapsed == 0, "paires d'entités DISTINCTES, pas de collapse"
    assert report.observed_pairs == [("organe", "organe")]


@schema_changes_suite.test()
async def test_preview_ecrit_rien_meme_compte(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    """preview=True calcule le même rapport que le run réel, sans écrire."""
    await _wipe(driver)
    await _seed_bx9(driver)
    await _seed_narrative(driver, "verin", "trappe", "règle")
    await _seed_narrative(driver, "verin", "trappe", "pilote")

    change = PromoteVerbs(
        verbe_slugs=[slugify("règle"), slugify("pilote")], rel_type="CONTROLS"
    )
    preview_report = await apply_schema_change(
        driver, change, project=PROJ, preview=True
    )

    assert await _narrative_count(driver) == 2, "preview : rien de supprimé"
    assert await _typed_edge(driver, "verin", "trappe", "CONTROLS") is None, (
        "preview : rien écrit"
    )

    real_report = await apply_schema_change(driver, change, project=PROJ, preview=False)

    assert preview_report.edges_converted == real_report.edges_converted == 2
    assert preview_report.edges_collapsed == real_report.edges_collapsed == 1
    assert preview_report.observed_pairs == real_report.observed_pairs
    assert preview_report.samples == real_report.samples


@schema_changes_suite.test()
async def test_promote_idempotent(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    """Rejouer le même changement une 2e fois ne convertit plus rien (déjà fait)."""
    await _wipe(driver)
    await _seed_bx9(driver)
    await _seed_narrative(driver, "verin", "trappe", "règle")

    change = PromoteVerbs(verbe_slugs=[slugify("règle")], rel_type="CONTROLS")
    first = await apply_schema_change(driver, change, project=PROJ)
    second = await apply_schema_change(driver, change, project=PROJ)

    assert first.edges_converted == 1
    assert second.edges_converted == 0
    assert second.edges_collapsed == 0


@schema_changes_suite.test()
async def test_promote_etancheite_projet(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    """Le changement appliqué dans le projet A laisse le projet B intact."""
    await _wipe(driver)
    await _seed_bx9(driver)
    await _seed_narrative(driver, "verin", "trappe", "règle")
    await _seed_bx9(driver, proj=PROJ_B)
    await _seed_narrative(driver, "verin", "trappe", "règle", proj=PROJ_B)

    change = PromoteVerbs(verbe_slugs=[slugify("règle")], rel_type="CONTROLS")
    await apply_schema_change(driver, change, project=PROJ)

    assert await _typed_edge(driver, "verin", "trappe", "CONTROLS") is not None
    assert await _typed_edge(driver, "verin", "trappe", "CONTROLS", proj=PROJ_B) is None
    assert await _narrative_count(driver, proj=PROJ_B) == 1, "projet B intact"


@schema_changes_suite.test()
async def test_promote_report_exposes_original_verbatim_verbs(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    """report.verbes porte les verbes VERBATIM d'origine, dédupliqués — matériau
    de l'évolution du profil (core.profile_evolution.evolve_profile)."""
    await _wipe(driver)
    await _seed_bx9(driver)
    await _seed_narrative(driver, "verin", "trappe", "règle")
    await _seed_narrative(driver, "levier", "pression", "pilote")

    change = PromoteVerbs(
        verbe_slugs=[slugify("règle"), slugify("pilote")], rel_type="CONTROLS"
    )
    report = await apply_schema_change(driver, change, project=PROJ)

    assert sorted(report.verbes) == ["pilote", "règle"]


@schema_changes_suite.test()
async def test_promote_report_verbes_deduplicated_same_pair(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    await _wipe(driver)
    await _seed_bx9(driver)
    await _seed_narrative(driver, "verin", "trappe", "règle")

    change = PromoteVerbs(verbe_slugs=[slugify("règle")], rel_type="CONTROLS")
    report = await apply_schema_change(driver, change, project=PROJ)

    assert report.verbes == ["règle"]


@schema_changes_suite.test()
async def test_merge_types_report_has_no_verbes(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    """MergeTypes ne porte pas de verbes (champ par défaut vide, réservé à PromoteVerbs)."""
    await _wipe(driver)
    await _seed_entity(driver, "piston1", "Piston 1", "piston")

    change = MergeTypes(sources=["piston"], target="organe")
    report = await apply_schema_change(driver, change, project=PROJ)

    assert report.verbes == []


# ──────────────────── MergeTypes ────────────────────


@schema_changes_suite.test()
async def test_merge_types_nominal(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    """Deux types-paraphrases ('piston', 'cylindre') fusionnés dans 'organe'."""
    await _wipe(driver)
    await _seed_entity(driver, "piston1", "Piston 1", "piston")
    await _seed_entity(driver, "piston2", "Piston 2", "piston")
    await _seed_entity(driver, "cylindre1", "Cylindre 1", "cylindre")
    await _seed_entity(driver, "levier", "Levier", "commande")  # témoin, pas touché

    change = MergeTypes(sources=["piston", "cylindre"], target="organe")
    report = await apply_schema_change(driver, change, project=PROJ)

    assert report.entities_retyped == 3
    assert await _entity_type(driver, "piston1") == "organe"
    assert await _entity_type(driver, "piston2") == "organe"
    assert await _entity_type(driver, "cylindre1") == "organe"
    assert await _entity_type(driver, "levier") == "commande", "témoin non touché"
    assert len(report.samples) == 3


@schema_changes_suite.test()
async def test_merge_types_rename_source_unique(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    """Un renommage est une fusion à UNE seule source."""
    await _wipe(driver)
    await _seed_entity(driver, "verin1", "Vérin 1", "verin_hydro")

    change = MergeTypes(sources=["verin_hydro"], target="organe")
    report = await apply_schema_change(driver, change, project=PROJ)

    assert report.entities_retyped == 1
    assert await _entity_type(driver, "verin1") == "organe"


@schema_changes_suite.test()
async def test_merge_types_idempotent(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    """Rejouer la même fusion une 2e fois ne retype plus rien."""
    await _wipe(driver)
    await _seed_entity(driver, "piston1", "Piston 1", "piston")

    change = MergeTypes(sources=["piston"], target="organe")
    first = await apply_schema_change(driver, change, project=PROJ)
    second = await apply_schema_change(driver, change, project=PROJ)

    assert first.entities_retyped == 1
    assert second.entities_retyped == 0


@schema_changes_suite.test()
async def test_merge_types_etancheite_projet(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    """La fusion appliquée dans le projet A laisse le projet B intact."""
    await _wipe(driver)
    await _seed_entity(driver, "piston1", "Piston 1", "piston")
    await _seed_entity(driver, "piston1", "Piston 1", "piston", proj=PROJ_B)

    change = MergeTypes(sources=["piston"], target="organe")
    await apply_schema_change(driver, change, project=PROJ)

    assert await _entity_type(driver, "piston1") == "organe"
    assert await _entity_type(driver, "piston1", proj=PROJ_B) == "piston", (
        "projet B intact"
    )


@schema_changes_suite.test()
async def test_merge_types_machinerie_sources_deja_cible_autorise(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    """Cible machinerie ('evenement') autorisée SI toutes les sources sont déjà ce type."""
    await _wipe(driver)
    await _seed_entity(driver, "ev1", "Un événement", "evenement")

    change = MergeTypes(sources=["evenement"], target="evenement")
    report = await apply_schema_change(driver, change, project=PROJ, preview=True)

    assert report.entities_retyped == 1


# ──────────────────── Refus ────────────────────


@schema_changes_suite.test()
async def test_refus_promote_vers_lie_a(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    await _wipe(driver)
    change = PromoteVerbs(verbe_slugs=["regle"], rel_type="LIE_A")
    with raises(ValueError, match="LIE_A"):
        await apply_schema_change(driver, change, project=PROJ)


@schema_changes_suite.test()
async def test_refus_rel_type_vide(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    await _wipe(driver)
    change = PromoteVerbs(verbe_slugs=["regle"], rel_type="")
    with raises(ValueError):
        await apply_schema_change(driver, change, project=PROJ)


@schema_changes_suite.test()
async def test_refus_rel_type_non_upper_snake(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    await _wipe(driver)
    change = PromoteVerbs(verbe_slugs=["regle"], rel_type="controls")
    with raises(ValueError):
        await apply_schema_change(driver, change, project=PROJ)


@schema_changes_suite.test()
async def test_refus_rel_type_machinerie(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    await _wipe(driver)
    change = PromoteVerbs(verbe_slugs=["regle"], rel_type="INVOLVES")
    with raises(ValueError, match="INVOLVES"):
        await apply_schema_change(driver, change, project=PROJ)

    change2 = PromoteVerbs(verbe_slugs=["regle"], rel_type="NEXT")
    with raises(ValueError, match="NEXT"):
        await apply_schema_change(driver, change2, project=PROJ)

    change3 = PromoteVerbs(verbe_slugs=["regle"], rel_type="DESCRIBED_IN")
    with raises(ValueError, match="DESCRIBED_IN"):
        await apply_schema_change(driver, change3, project=PROJ)


@schema_changes_suite.test()
async def test_refus_merge_types_vers_evenement(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    await _wipe(driver)
    change = MergeTypes(sources=["organe"], target="evenement")
    with raises(ValueError, match="evenement"):
        await apply_schema_change(driver, change, project=PROJ)


@schema_changes_suite.test()
async def test_refus_merge_types_vers_document(
    driver: Annotated[AsyncDriver, Use(_schema_driver)],
) -> None:
    await _wipe(driver)
    change = MergeTypes(sources=["organe"], target="document")
    with raises(ValueError, match="document"):
        await apply_schema_change(driver, change, project=PROJ)
