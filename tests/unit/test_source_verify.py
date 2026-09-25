"""Vérification SOURCE d'une alerte de cohérence (#vérif-source) — distingue
une VRAIE incohérence du document d'une mauvaise LECTURE de Felix à
l'extraction. Deux familles de tests, aucun appel LLM réel :

- `verify_against_source` (felix.core.check) : câblage ledger, repli
  `unverifiable` SANS appel LLM quand aucune page source, kind/correction
  transmis tels que rendus par le modèle — Agent construit avec `FunctionModel`
  (pydantic-ai, stub IN-PROCESS, cf. tests/unit/test_cost.py pour TestModel) :
  ça permet de CONTRÔLER le verdict rendu (TestModel ne le permet pas).
- `consistency_alerts` (felix.atelier.pipeline) : routage du `kind` vers le
  titre de la carte + `correction`, et coût constant « un appel PAR ALERTE
  DISTINCTE, jamais par entité » — `consistency_check`/`verify_against_source`/
  `record_alert` sont patchés (aucun driver Neo4j nécessaire pour ce câblage).

Noms univers isolé pour ces tests — inédits : Riantel, Doshka.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from protest import ProTestSuite
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from felix.atelier.pipeline import consistency_alerts
from felix.core.check import CheckVerdict, SourceVerdict, verify_against_source
from felix.core.deps import GenericDeps
from felix.cost import CostLedger

source_verify_suite = ProTestSuite("SourceVerify")


def _make_verifier(output: dict) -> Agent[None, SourceVerdict]:
    """Agent `FunctionModel` qui rend TOUJOURS `output` comme SourceVerdict —
    contrôle total du verdict (TestModel seul ne le permet pas), sans appel réseau."""

    async def respond(_messages: list, info: AgentInfo) -> ModelResponse:
        tool_name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name=tool_name, args=output)])

    return Agent(FunctionModel(respond), output_type=SourceVerdict)


def _boom_verifier() -> Agent[None, SourceVerdict]:
    """Un Agent qui explose s'il est appelé — preuve qu'AUCUN appel LLM n'a
    lieu quand il n'y a pas de page source (repli `unverifiable` en code)."""

    async def respond(_messages: list, _info: AgentInfo) -> ModelResponse:
        msg = (
            "verify_against_source ne doit JAMAIS appeler le verifier sans page source"
        )
        raise AssertionError(msg)

    return Agent(FunctionModel(respond), output_type=SourceVerdict)


_VERDICT = CheckVerdict(
    reason="r",
    contradiction=True,
    message="Corps de l'alerte de test.",
    sujets=["Riantel"],
)


# ──────────────────── verify_against_source ────────────────────


@source_verify_suite.test()
async def test_verify_against_source_skips_llm_when_no_pages() -> None:
    ledger = CostLedger()
    result = await verify_against_source(
        _VERDICT, [], ledger, verifier=_boom_verifier()
    )
    assert result.kind == "unverifiable"
    assert ledger.summary().total_tokens == 0


@source_verify_suite.test()
async def test_verify_against_source_document_kind_records_ledger_usage() -> None:
    ledger = CostLedger()
    verifier = _make_verifier(
        {
            "reason": "le bon de livraison affiche deux poids totaux différents",
            "kind": "document",
            "explanation": "le document se contredit lui-même",
            "correction": "",
        }
    )
    pages = [("Bon de livraison Riantel", 1, "texte source")]
    result = await verify_against_source(_VERDICT, pages, ledger, verifier=verifier)
    assert result.kind == "document"
    assert result.correction == ""
    summary = ledger.summary()
    assert summary.total_tokens > 0
    assert len(summary.by_model) == 1


@source_verify_suite.test()
async def test_verify_against_source_extraction_kind_carries_correction() -> None:
    ledger = CostLedger()
    verifier = _make_verifier(
        {
            "reason": "le total extrait est le poids d'un seul carton, pas le total",
            "kind": "extraction",
            "explanation": "Felix a confondu le poids d'un carton avec le total",
            "correction": "poids total de la livraison : 72 kg, d'après la page 1",
        }
    )
    pages = [("Bon de livraison Doshka", 1, "6 cartons de 12 kg, total 72 kg")]
    result = await verify_against_source(_VERDICT, pages, ledger, verifier=verifier)
    assert result.kind == "extraction"
    assert result.correction == "poids total de la livraison : 72 kg, d'après la page 1"


@source_verify_suite.test()
async def test_verify_against_source_without_ledger_still_works() -> None:
    verifier = _make_verifier(
        {
            "reason": "r",
            "kind": "document",
            "explanation": "e",
            "correction": "",
        }
    )
    pages = [("Bon de livraison Riantel", 1, "texte")]
    result = await verify_against_source(_VERDICT, pages, None, verifier=verifier)
    assert result.kind == "document"


# ──────────────────── consistency_alerts : routage kind → titre/correction ────────────────────

_ALERT_PROJ = "test-source-verify-alerts-v1"


async def _stub_check(
    driver,
    ref,
    write_log,
    profile,
    *,
    project,
    cost_ledger=None,
) -> CheckVerdict:
    return CheckVerdict(
        reason="r",
        contradiction=True,
        message="Corps de test.",
        sujets=["Riantel", "Doshka"],
    )


async def _stub_source_pages(driver, sujets, *, project):
    return []


async def _noop_record_alert(driver, body, *, project):
    return None


def _stub_verify(kind: str, correction: str = ""):
    async def _verify(verdict, pages, ledger=None, *, verifier=None) -> SourceVerdict:
        return SourceVerdict(
            reason="r", kind=kind, explanation="e", correction=correction
        )

    return _verify


@source_verify_suite.test()
async def test_consistency_alerts_document_kind_gets_document_title() -> None:
    deps = GenericDeps(driver=None, project_id=_ALERT_PROJ)  # type: ignore[arg-type]
    deps.check_candidates = {"riantel"}
    with (
        patch("felix.atelier.pipeline.consistency_check", _stub_check),
        patch("felix.atelier.pipeline._source_pages_for_subjects", _stub_source_pages),
        patch("felix.atelier.pipeline.verify_against_source", _stub_verify("document")),
        patch("felix.atelier.pipeline.record_alert", _noop_record_alert),
    ):
        events = [ev async for ev in consistency_alerts(None, deps, None)]  # type: ignore[arg-type]
    assert len(events) == 1
    payload = json.loads(events[0].data)
    assert payload["title"] == "Incohérence dans le document"
    assert payload["source_kind"] == "document"
    assert payload["correction"] == ""


@source_verify_suite.test()
async def test_consistency_alerts_extraction_kind_gets_calmer_title_and_correction() -> (
    None
):
    deps = GenericDeps(driver=None, project_id=_ALERT_PROJ)  # type: ignore[arg-type]
    deps.check_candidates = {"riantel"}
    correction = "poids total de la livraison : 72 kg, d'après la page 1"
    with (
        patch("felix.atelier.pipeline.consistency_check", _stub_check),
        patch("felix.atelier.pipeline._source_pages_for_subjects", _stub_source_pages),
        patch(
            "felix.atelier.pipeline.verify_against_source",
            _stub_verify("extraction", correction),
        ),
        patch("felix.atelier.pipeline.record_alert", _noop_record_alert),
    ):
        events = [ev async for ev in consistency_alerts(None, deps, None)]  # type: ignore[arg-type]
    payload = json.loads(events[0].data)
    assert payload["title"] == "Felix a peut-être mal lu le document"
    assert payload["source_kind"] == "extraction"
    assert payload["correction"] == correction


@source_verify_suite.test()
async def test_consistency_alerts_unverifiable_kind_keeps_default_title() -> None:
    deps = GenericDeps(driver=None, project_id=_ALERT_PROJ)  # type: ignore[arg-type]
    deps.check_candidates = {"riantel"}
    with (
        patch("felix.atelier.pipeline.consistency_check", _stub_check),
        patch("felix.atelier.pipeline._source_pages_for_subjects", _stub_source_pages),
        patch(
            "felix.atelier.pipeline.verify_against_source", _stub_verify("unverifiable")
        ),
        patch("felix.atelier.pipeline.record_alert", _noop_record_alert),
    ):
        events = [ev async for ev in consistency_alerts(None, deps, None)]  # type: ignore[arg-type]
    payload = json.loads(events[0].data)
    assert payload["title"] == "Incohérence possible"
    assert payload["source_kind"] == "unverifiable"


@source_verify_suite.test()
async def test_consistency_alerts_calls_verifier_once_per_distinct_alert() -> None:
    """Coût constant : deux entités candidates qui remontent la MÊME
    contradiction (mêmes sujets) ne doivent déclencher le vérificateur
    qu'UNE fois — jamais par entité (cf. CLAUDE.md, coût dominé par les
    appels répétés)."""
    calls: list[CheckVerdict] = []

    async def _counting_verify(
        verdict, pages, ledger=None, *, verifier=None
    ) -> SourceVerdict:
        calls.append(verdict)
        return SourceVerdict(reason="r", kind="document")

    deps = GenericDeps(driver=None, project_id=_ALERT_PROJ)  # type: ignore[arg-type]
    deps.check_candidates = {"riantel", "doshka"}
    with (
        patch("felix.atelier.pipeline.consistency_check", _stub_check),
        patch("felix.atelier.pipeline._source_pages_for_subjects", _stub_source_pages),
        patch("felix.atelier.pipeline.verify_against_source", _counting_verify),
        patch("felix.atelier.pipeline.record_alert", _noop_record_alert),
    ):
        events = [ev async for ev in consistency_alerts(None, deps, None)]  # type: ignore[arg-type]
    assert len(events) == 1, "une seule contradiction distincte → une seule carte"
    assert len(calls) == 1, (
        "verify_against_source doit être appelé UNE fois par alerte distincte"
    )
