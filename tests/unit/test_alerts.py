"""Alertes de cohérence (#50-a) — méta-nœud :Alert, consume-and-mark, isolation projet.

Tests purs (render_alerts_block) + tests avec driver Neo4j réel (record / consume /
étanchéité). Les tests avec driver utilisent la fixture protest standard (async
generator, max_concurrency=1).

Noms univers isolé : Korvax, Weldra, Thyren — inédits (anti-leakage vérifié dans
test_no_test_names_in_prompts ci-dessous).
"""
from __future__ import annotations

import pathlib
import re
from typing import TYPE_CHECKING, Annotated

from protest import ProTestSuite, Use, fixture

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

from felix.core.alerts import (
    consume_unnotified_alerts,
    record_alert,
    render_alerts_block,
)
from felix.graph.driver import get_driver, setup_constraints

alerts_suite = ProTestSuite("Alerts")

# Noms dédiés à ces tests — univers isolé (anti-leakage vérifié ci-dessous).
_TEST_NAMES = ("Korvax", "Weldra", "Thyren")


# ─────────────────────── Fixture driver réel ───────────────────────────────────

@fixture(max_concurrency=1)
async def _alert_driver() -> AsyncGenerator[AsyncDriver]:
    """Ouvre un driver Neo4j pour la suite ; le ferme en teardown."""
    driver = get_driver()
    await setup_constraints(driver)
    try:
        yield driver
    finally:
        await driver.close()


# ─────────────────────── Tests PURS (sans driver) ─────────────────────────────

@alerts_suite.test()
def test_render_empty_alerts_is_empty() -> None:
    """Aucune alerte → chaîne vide, le prompt reste nu (cas nominal)."""
    assert render_alerts_block([]) == ""


@alerts_suite.test()
def test_render_single_alert_contains_body() -> None:
    """Le bloc inclut le corps de l'alerte telle quelle."""
    block = render_alerts_block(["Korvax ne peut pas agir après sa mort"])
    assert "Korvax ne peut pas agir après sa mort" in block


@alerts_suite.test()
def test_render_block_is_marked_as_context() -> None:
    """Balisé comme contexte (crochet ouvrant) : le maître ne l'extrait pas comme récit."""
    block = render_alerts_block(["Weldra est déjà partie"])
    assert block.startswith("[")


@alerts_suite.test()
def test_render_block_contains_signalement_instruction() -> None:
    """Le bloc demande de signaler sobrement — jamais de questionner (persona bloc-notes)."""
    block = render_alerts_block(["Thyren est présent après sa mort"])
    low = block.lower()
    # La consigne doit inclure « signale » (SIGNALE-LE ou signalement).
    assert "signal" in low
    # Et NE DOIT PAS inviter à questionner.
    assert "question" not in low or "sans question" in low


@alerts_suite.test()
def test_render_multiple_alerts_contains_all_bodies() -> None:
    """Plusieurs alertes → toutes les phrases sont dans le bloc, séparées."""
    bodies = ["Korvax mort au chapitre 2", "Weldra absente ce jour-là"]
    block = render_alerts_block(bodies)
    assert "Korvax mort au chapitre 2" in block
    assert "Weldra absente ce jour-là" in block


# ──────────── Tests avec driver réel (Neo4j) ─────────────────────────────────

@alerts_suite.test()
async def test_record_then_consume_returns_body(
    driver: Annotated[AsyncDriver, Use(_alert_driver)],
) -> None:
    """record_alert + consume_unnotified_alerts retourne le corps et marque notified."""
    proj = "test-alerts-record-v1"
    async with driver.session() as session:
        await session.run("MATCH (a:Alert {project: $p}) DETACH DELETE a", p=proj)
    try:
        await record_alert(driver, "Korvax ne peut pas agir après sa mort", project=proj)
        bodies = await consume_unnotified_alerts(driver, project=proj)
        assert bodies == ["Korvax ne peut pas agir après sa mort"]
        # L'alerte doit être marquée notified=true en base.
        async with driver.session() as session:
            result = await session.run(
                "MATCH (a:Alert {project: $p}) RETURN a.notified AS n", p=proj
            )
            rows = await result.data()
        assert rows and all(r["n"] for r in rows), "l'alerte doit être notifiée en base"
    finally:
        async with driver.session() as session:
            await session.run("MATCH (a:Alert {project: $p}) DETACH DELETE a", p=proj)


@alerts_suite.test()
async def test_second_consume_returns_empty(
    driver: Annotated[AsyncDriver, Use(_alert_driver)],
) -> None:
    """Un second consume retourne [] — on n'annonce pas deux fois au maître."""
    proj = "test-alerts-second-v1"
    async with driver.session() as session:
        await session.run("MATCH (a:Alert {project: $p}) DETACH DELETE a", p=proj)
    try:
        await record_alert(driver, "Weldra est déjà partie", project=proj)
        await consume_unnotified_alerts(driver, project=proj)
        second = await consume_unnotified_alerts(driver, project=proj)
        assert second == [], "le second consume doit être vide (déjà notifié)"
    finally:
        async with driver.session() as session:
            await session.run("MATCH (a:Alert {project: $p}) DETACH DELETE a", p=proj)


@alerts_suite.test()
async def test_project_isolation(
    driver: Annotated[AsyncDriver, Use(_alert_driver)],
) -> None:
    """Une alerte du projet A n'apparaît pas dans les lectures du projet B."""
    proj_a = "test-alerts-iso-a-v1"
    proj_b = "test-alerts-iso-b-v1"
    for p in (proj_a, proj_b):
        async with driver.session() as session:
            await session.run("MATCH (a:Alert {project: $p}) DETACH DELETE a", p=p)
    try:
        await record_alert(driver, "Thyren ne peut pas être là", project=proj_a)
        bodies_b = await consume_unnotified_alerts(driver, project=proj_b)
        assert bodies_b == [], f"alerte de {proj_a} visible dans {proj_b} : contamination"
        bodies_a = await consume_unnotified_alerts(driver, project=proj_a)
        assert bodies_a == ["Thyren ne peut pas être là"]
    finally:
        for p in (proj_a, proj_b):
            async with driver.session() as session:
                await session.run("MATCH (a:Alert {project: $p}) DETACH DELETE a", p=p)


# ─────────────────────────── Anti-leakage ────────────────────────────────────

@alerts_suite.test()
def test_no_test_names_in_prompts() -> None:
    """Les noms utilisés par ces tests n'entrent JAMAIS dans les prompts des agents.
    Match mot entier : « Korvax » ne doit pas matcher dans un mot plus long."""
    src = pathlib.Path(__file__).parents[3] / "src" / "felix"
    leaked = []
    for py in src.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for name in _TEST_NAMES:
            if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
                leaked.append(f"{name} dans {py.relative_to(src.parent.parent)}")
    assert not leaked, f"noms de test présents dans les sources : {leaked}"


# ─────────── dédup des verdicts : une contradiction, une carte ───────────
# Le juge tourne PAR entité candidate : une même contradiction entre Korvax et
# Weldra remonte depuis chacune, reformulée → la clé « texte exact » ne dédupe
# pas (9 cartes quasi identiques vues en ingestion). La clé est l'ensemble des
# SUJETS impliqués ; un ensemble inclus dans un autre = même contradiction.
from felix.core.check import CheckVerdict, distinct_contradictions  # noqa: E402


def _v(message: str, sujets: list[str], *, contradiction: bool = True) -> CheckVerdict:
    return CheckVerdict(reason="r", contradiction=contradiction, message=message,
                        sujets=sujets)


@alerts_suite.test()
def test_distinct_contradictions_merges_same_subjects_rephrased() -> None:
    kept = distinct_contradictions([
        _v("Korvax ne peut pas dépasser Weldra.", ["Korvax", "Weldra"]),
        _v("La valeur de Weldra rend Korvax impossible.", ["weldra", "Korvax "]),
        _v("Korvax, Weldra et Thyren s'excluent.", ["Korvax", "Weldra", "Thyren"]),
    ])
    assert [k.message for k in kept] == ["Korvax ne peut pas dépasser Weldra."]


@alerts_suite.test()
def test_distinct_contradictions_keeps_disjoint_and_drops_non_contradictions() -> None:
    kept = distinct_contradictions([
        _v("A", ["Korvax", "Weldra"]),
        _v("B", ["Thyren"]),
        _v("C", ["Korvax"], contradiction=False),
    ])
    assert [k.message for k in kept] == ["A", "B"]


@alerts_suite.test()
def test_distinct_contradictions_without_subjects_falls_back_to_text() -> None:
    kept = distinct_contradictions([_v("Même phrase", []), _v("même phrase ", []),
                                    _v("Autre", [])])
    assert [k.message for k in kept] == ["Même phrase", "Autre"]
