"""Comptabilité des coûts LLM (#coût) — TDD red→green.

Trois familles de tests :
- CostLedger (calcul pur, sans driver ni LLM) : agrégation par modèle, prix
  inconnu → null, jamais un faux 0.
- pricing (table par défaut + surcharge FLX_PRICING_JSON) : fonctions pures.
- câblage consistency_check → cost_ledger (le judge du check N'ÉTAIT COMPTÉ
  NULLE PART avant) : Agent construit avec `TestModel` de pydantic-ai — un stub
  IN-PROCESS sans aucun appel réseau, pas un « live LLM call ».
- persistance :CostEntry par projet + agrégation (GET /api/costs), isolation
  inter-projets (driver Neo4j réel, même fixture que test_alerts.py).

Noms univers isolé pour les entités de test : Zorvun, Kelphi (inédits — pas de
recoupement avec les autres suites, même si l'anti-leakage n'y est vérifié que
dans src/felix, pas entre suites de tests)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from protest import ProTestSuite, Use, fixture
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

from felix.config import settings
from felix.core import create_entity
from felix.core.check import CheckVerdict, consistency_check
from felix.core.costs import project_cost_totals, record_cost_entry
from felix.cost import (
    DEFAULT_PRICING,
    CostLedger,
    CostSummary,
    build_pricing_table,
    parse_pricing_overrides,
    price_for_model,
)
from felix.graph.driver import get_driver, setup_constraints

cost_suite = ProTestSuite("Cost")


# ─────────────────────── CostLedger : calcul pur ────────────────────────

@cost_suite.test()
def test_single_known_model_computes_cost() -> None:
    ledger = CostLedger()
    ledger.add("mistral-small-latest", 1_000_000, 1_000_000)
    s = ledger.summary()
    assert s.request_tokens == 1_000_000
    assert s.response_tokens == 1_000_000
    assert s.total_tokens == 2_000_000
    assert s.cost_usd == 0.75  # 0.15 (input) + 0.60 (output) $/M


@cost_suite.test()
def test_unknown_model_has_null_cost_never_a_fake_zero() -> None:
    ledger = CostLedger()
    ledger.add("un-modele-jamais-vu", 1000, 500)
    s = ledger.summary()
    assert s.cost_usd is None
    assert s.by_model[0].cost_usd is None


@cost_suite.test()
def test_mixed_models_total_is_null_but_known_model_keeps_its_own_cost() -> None:
    """Un total qui ignorerait silencieusement le modèle inconnu sous-estimerait
    la dépense réelle — le total est null dès qu'UN SEUL modèle est inconnu,
    mais chaque modèle CONNU garde son propre cost_usd (détail exploitable)."""
    ledger = CostLedger()
    ledger.add("mistral-small-latest", 1_000_000, 0)
    ledger.add("un-modele-jamais-vu", 1000, 500)
    s = ledger.summary()
    assert s.cost_usd is None
    by_name = {m.model: m for m in s.by_model}
    assert by_name["mistral-small-latest"].cost_usd == 0.15
    assert by_name["un-modele-jamais-vu"].cost_usd is None


@cost_suite.test()
def test_same_model_multiple_calls_aggregates_tokens() -> None:
    ledger = CostLedger()
    ledger.add("devstral-2512", 100, 50)
    ledger.add("devstral-2512", 200, 100)
    s = ledger.summary()
    assert len(s.by_model) == 1
    assert s.by_model[0].request_tokens == 300
    assert s.by_model[0].response_tokens == 150
    assert s.by_model[0].total_tokens == 450


@cost_suite.test()
def test_merge_combines_two_ledgers() -> None:
    """Même usage que le merge des touched_ids d'ingestion (chunk → document)."""
    a = CostLedger()
    a.add("mistral-small-latest", 100, 50)
    b = CostLedger()
    b.add("mistral-small-latest", 200, 100)
    a.merge(b)
    s = a.summary()
    assert len(s.by_model) == 1
    assert s.by_model[0].request_tokens == 300
    assert s.by_model[0].response_tokens == 150


@cost_suite.test()
def test_empty_ledger_has_known_zero_cost() -> None:
    """Aucun appel LLM → coût 0 CONNU (différent de « prix inconnu » : ici il
    n'y a simplement rien à facturer)."""
    s = CostLedger().summary()
    assert s.total_tokens == 0
    assert s.cost_usd == 0.0
    assert s.by_model == []


@cost_suite.test()
def test_add_usage_reads_input_output_tokens() -> None:
    """add_usage lit .input_tokens/.output_tokens d'un RunUsage pydantic-ai
    (pas les alias dépréciés request_tokens/response_tokens)."""
    ledger = CostLedger()
    ledger.add_usage("mistral-large-latest", RunUsage(input_tokens=10, output_tokens=5))
    s = ledger.summary()
    assert s.request_tokens == 10
    assert s.response_tokens == 5


# ─────────────────────── pricing : table + surcharge ────────────────────

@cost_suite.test()
def test_default_pricing_has_all_required_models() -> None:
    for name in (
        "devstral-2512", "devstral-small-2512", "mistral-small-latest",
        "mistral-small-2506", "mistral-large-latest", "mistral-medium-latest",
    ):
        assert name in DEFAULT_PRICING, f"prix par défaut manquant pour {name}"


@cost_suite.test()
def test_pricing_override_replaces_a_default_entirely() -> None:
    table = build_pricing_table('{"mistral-small-latest": {"input": 9.0, "output": 9.0}}')
    assert table["mistral-small-latest"].input_per_million == 9.0
    assert table["mistral-small-latest"].output_per_million == 9.0
    # Les autres défauts restent actifs (pas une table qui remplace tout).
    assert table["mistral-large-latest"] == DEFAULT_PRICING["mistral-large-latest"]


@cost_suite.test()
def test_pricing_override_can_add_an_unlisted_model() -> None:
    table = build_pricing_table('{"mon-modele-local": {"input": 0.0, "output": 0.0}}')
    assert table["mon-modele-local"].input_per_million == 0.0


@cost_suite.test()
def test_pricing_override_invalid_json_falls_back_to_defaults() -> None:
    table = build_pricing_table("{ceci n'est pas du json")
    assert table["devstral-2512"] == DEFAULT_PRICING["devstral-2512"]


@cost_suite.test()
def test_pricing_override_empty_string_is_defaults_only() -> None:
    assert build_pricing_table("") == DEFAULT_PRICING


@cost_suite.test()
def test_pricing_reads_settings_env_override_when_no_explicit_arg() -> None:
    """Simule FLX_PRICING_JSON : la surcharge lue par pydantic-settings depuis
    l'env finit dans settings.pricing_json — build_pricing_table() SANS argument
    explicite doit la reprendre."""
    original = settings.pricing_json
    try:
        settings.pricing_json = '{"mistral-small-latest": {"input": 1.23, "output": 4.56}}'
        table = build_pricing_table()
        assert table["mistral-small-latest"].input_per_million == 1.23
        assert table["mistral-small-latest"].output_per_million == 4.56
    finally:
        settings.pricing_json = original


@cost_suite.test()
def test_parse_pricing_overrides_skips_invalid_entry_keeps_valid() -> None:
    out = parse_pricing_overrides('{"bon": {"input": 1, "output": 2}, "mauvais": {"input": "x"}}')
    assert "bon" in out
    assert "mauvais" not in out


@cost_suite.test()
def test_parse_pricing_overrides_non_object_json_is_ignored() -> None:
    assert parse_pricing_overrides("[1, 2, 3]") == {}


@cost_suite.test()
def test_price_for_model_unknown_returns_none() -> None:
    assert price_for_model("un-modele-totalement-inconnu") is None


# ─────────────────────── Fixture driver réel (Neo4j) ────────────────────

@fixture(max_concurrency=1)
async def _cost_driver() -> AsyncGenerator[AsyncDriver]:
    driver = get_driver()
    await setup_constraints(driver)
    try:
        yield driver
    finally:
        await driver.close()


# ─────────── câblage consistency_check → cost_ledger (TestModel) ────────

@cost_suite.test()
async def test_consistency_check_records_usage_in_ledger(
    driver: Annotated[AsyncDriver, Use(_cost_driver)],
) -> None:
    """Le judge du check de cohérence n'était compté NULLE PART avant (#coût).
    `TestModel` (pydantic-ai) est un stub IN-PROCESS : aucun appel réseau — on
    vérifie le câblage (le ledger reçoit bien le modèle + les tokens), pas le
    raisonnement du modèle (hors sujet ici, et interdit par la consigne no-LLM)."""
    proj = "test-cost-check-zorvun-v1"
    async with driver.session() as session:
        await session.run("MATCH (e:GenEntity {project: $p}) DETACH DELETE e", p=proj)
    try:
        await create_entity(driver, "zorvun", "Zorvun", "personnage", {}, project=proj)
        ledger = CostLedger()
        judge = Agent(TestModel(), output_type=CheckVerdict)
        verdict = await consistency_check(
            driver, "zorvun", None, None,
            project=proj, cost_ledger=ledger, judge=judge,
        )
        assert isinstance(verdict, CheckVerdict)
        summary = ledger.summary()
        assert summary.total_tokens > 0
        assert len(summary.by_model) == 1
        assert summary.by_model[0].model == "test"
        # "test" est absent de la table de prix → prix inconnu, jamais un faux 0.
        assert summary.cost_usd is None
    finally:
        async with driver.session() as session:
            await session.run("MATCH (e:GenEntity {project: $p}) DETACH DELETE e", p=proj)


@cost_suite.test()
async def test_consistency_check_without_ledger_still_works(
    driver: Annotated[AsyncDriver, Use(_cost_driver)],
) -> None:
    """`cost_ledger` est optionnel — les appelants qui ne le fournissent pas
    (anciens tests, scripts) ne doivent pas casser."""
    proj = "test-cost-check-kelphi-v1"
    async with driver.session() as session:
        await session.run("MATCH (e:GenEntity {project: $p}) DETACH DELETE e", p=proj)
    try:
        await create_entity(driver, "kelphi", "Kelphi", "personnage", {}, project=proj)
        judge = Agent(TestModel(), output_type=CheckVerdict)
        verdict = await consistency_check(
            driver, "kelphi", None, None, project=proj, judge=judge,
        )
        assert isinstance(verdict, CheckVerdict)
    finally:
        async with driver.session() as session:
            await session.run("MATCH (e:GenEntity {project: $p}) DETACH DELETE e", p=proj)


@cost_suite.test()
async def test_consistency_check_missing_entity_never_calls_judge(
    driver: Annotated[AsyncDriver, Use(_cost_driver)],
) -> None:
    """Entité introuvable → retour anticipé AVANT construction du judge : le
    ledger fourni reste vide (aucun appel LLM à compter)."""
    proj = "test-cost-check-missing-v1"
    ledger = CostLedger()
    verdict = await consistency_check(
        driver, "entite-zzz-inexistante", None, None, project=proj, cost_ledger=ledger,
    )
    assert verdict.contradiction is False
    assert ledger.summary().total_tokens == 0


# ─────────── persistance :CostEntry + agrégation (/api/costs) ───────────

@cost_suite.test()
async def test_record_cost_entry_then_totals_aggregates_by_kind(
    driver: Annotated[AsyncDriver, Use(_cost_driver)],
) -> None:
    proj = "test-cost-entries-v1"
    async with driver.session() as session:
        await session.run("MATCH (e:CostEntry {project: $p}) DETACH DELETE e", p=proj)
    try:
        chat = CostSummary(
            request_tokens=100, response_tokens=50, total_tokens=150,
            cost_usd=0.01, by_model=[],
        )
        ingest = CostSummary(
            request_tokens=200, response_tokens=100, total_tokens=300,
            cost_usd=0.02, by_model=[],
        )
        await record_cost_entry(driver, chat, project=proj, kind="chat")
        await record_cost_entry(driver, ingest, project=proj, kind="ingest")
        totals = await project_cost_totals(driver, project=proj)
        assert totals["request_tokens"] == 300
        assert totals["response_tokens"] == 150
        assert totals["total_tokens"] == 450
        assert round(totals["cost_usd"], 4) == 0.03
        assert totals["count_by_kind"] == {"chat": 1, "ingest": 1}
    finally:
        async with driver.session() as session:
            await session.run("MATCH (e:CostEntry {project: $p}) DETACH DELETE e", p=proj)


@cost_suite.test()
async def test_project_totals_null_when_one_entry_has_unknown_price(
    driver: Annotated[AsyncDriver, Use(_cost_driver)],
) -> None:
    proj = "test-cost-unknown-v1"
    async with driver.session() as session:
        await session.run("MATCH (e:CostEntry {project: $p}) DETACH DELETE e", p=proj)
    try:
        known = CostSummary(
            request_tokens=100, response_tokens=50, total_tokens=150,
            cost_usd=0.01, by_model=[],
        )
        unknown = CostSummary(
            request_tokens=10, response_tokens=5, total_tokens=15,
            cost_usd=None, by_model=[],
        )
        await record_cost_entry(driver, known, project=proj, kind="chat")
        await record_cost_entry(driver, unknown, project=proj, kind="chat")
        totals = await project_cost_totals(driver, project=proj)
        assert totals["cost_usd"] is None
        assert totals["total_tokens"] == 165
    finally:
        async with driver.session() as session:
            await session.run("MATCH (e:CostEntry {project: $p}) DETACH DELETE e", p=proj)


@cost_suite.test()
async def test_record_cost_entry_noop_when_zero_tokens(
    driver: Annotated[AsyncDriver, Use(_cost_driver)],
) -> None:
    """Un tour sans aucun appel LLM (salutation, pas d'extraction) ne pollue
    pas le registre de coûts du projet."""
    proj = "test-cost-noop-v1"
    async with driver.session() as session:
        await session.run("MATCH (e:CostEntry {project: $p}) DETACH DELETE e", p=proj)
    try:
        empty = CostSummary(
            request_tokens=0, response_tokens=0, total_tokens=0,
            cost_usd=0.0, by_model=[],
        )
        await record_cost_entry(driver, empty, project=proj, kind="chat")
        totals = await project_cost_totals(driver, project=proj)
        assert totals["total_tokens"] == 0
        assert totals["count_by_kind"] == {}
    finally:
        async with driver.session() as session:
            await session.run("MATCH (e:CostEntry {project: $p}) DETACH DELETE e", p=proj)


@cost_suite.test()
async def test_project_cost_isolation(
    driver: Annotated[AsyncDriver, Use(_cost_driver)],
) -> None:
    """Le coût de l'histoire A n'apparaît pas dans le total de l'histoire B —
    même loi que les alertes/messages/entités (#60)."""
    proj_a = "test-cost-iso-a-v1"
    proj_b = "test-cost-iso-b-v1"
    for p in (proj_a, proj_b):
        async with driver.session() as session:
            await session.run("MATCH (e:CostEntry {project: $p}) DETACH DELETE e", p=p)
    try:
        s = CostSummary(
            request_tokens=1000, response_tokens=500, total_tokens=1500,
            cost_usd=0.1, by_model=[],
        )
        await record_cost_entry(driver, s, project=proj_a, kind="chat")
        totals_b = await project_cost_totals(driver, project=proj_b)
        assert totals_b["total_tokens"] == 0, f"coût de {proj_a} visible dans {proj_b} : contamination"
        totals_a = await project_cost_totals(driver, project=proj_a)
        assert totals_a["total_tokens"] == 1500
    finally:
        for p in (proj_a, proj_b):
            async with driver.session() as session:
                await session.run("MATCH (e:CostEntry {project: $p}) DETACH DELETE e", p=p)
