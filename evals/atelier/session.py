"""Session protest du bot B (atelier) — séparée de la session legacy.

Run:
    protest eval evals.atelier.session:session
    just evals-atelier

Ne pas lancer en même temps que `just evals` : les cas atelier wipent le
graphe Neo4j partagé avant chaque run.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from protest import From, ProTestSession, Use
from protest.evals import EvalCase, EvalSuite, ModelLabel, TaskResult

from evals._judge import FelixJudge
from evals.atelier.dataset import (
    BAPTEME_DIFFERE_INPUTS,
    CHECK_ACT_THEN_DEATH_INPUTS,
    CHECK_DEATH_THEN_ACT_INPUTS,
    atelier_cases,
)
from evals.atelier.evaluators import multirun_majority

# Import runtime (pas TYPE_CHECKING) : protest résout les annotations des evals
# via get_type_hints — `TaskResult[AtelierRunResult]` doit être évaluable.
from evals.atelier.task import (
    AtelierRunResult,
    _bapteme_differe_check,
    _check_act_then_death,
    _check_death_then_act,
    atelier_driver,
    run_atelier_case,
    run_atelier_multirun_case,
)
from felix.config import settings

if TYPE_CHECKING:
    from neo4j import AsyncDriver

atelier_model = ModelLabel(
    name=settings.llm_chat_model or settings.llm_model, provider="mistral"
)

session = ProTestSession(history=True)
session.bind(atelier_driver)

atelier_suite = EvalSuite("atelier", model=atelier_model, judge=FelixJudge())
session.add_suite(atelier_suite)


@atelier_suite.eval()
async def atelier(
    case: Annotated[EvalCase, From(atelier_cases)],
    driver: Annotated[AsyncDriver, Use(atelier_driver)],
) -> TaskResult[AtelierRunResult]:
    return await run_atelier_case(driver, case.inputs)


@atelier_suite.eval(evaluators=[multirun_majority(threshold=2, total=3)])
async def bapteme_differe(
    driver: Annotated[AsyncDriver, Use(atelier_driver)],
) -> TaskResult[AtelierRunResult]:
    """Multi-run (N=3, seuil ≥2/3) — variance Mistral Small, pas une régression code.

    Le cas est joué 3 fois en série ; vert si ≥2 passes réussissent. Chaque
    pass repart d'un graphe vide grâce au wipe intégré dans run_atelier_case.
    Aucune concurrence pour éviter les 429 de l'API Mistral."""
    return await run_atelier_multirun_case(
        driver,
        BAPTEME_DIFFERE_INPUTS,
        n=3,
        check=_bapteme_differe_check,
    )


@atelier_suite.eval(evaluators=[multirun_majority(threshold=2, total=3)])
async def check_death_then_act(
    driver: Annotated[AsyncDriver, Use(atelier_driver)],
) -> TaskResult[AtelierRunResult]:
    """Multi-run (N=3, seuil ≥2/3) — variance du juge Mistral Small.

    Mort-puis-agit : le juge doit détecter l'impossibilité temporelle (alerte).
    Joué 3 fois en série ; vert si ≥2 passes émettent l'alerte attendue."""
    return await run_atelier_multirun_case(
        driver,
        CHECK_DEATH_THEN_ACT_INPUTS,
        n=3,
        check=_check_death_then_act,
    )


@atelier_suite.eval(evaluators=[multirun_majority(threshold=2, total=3)])
async def check_act_then_death(
    driver: Annotated[AsyncDriver, Use(atelier_driver)],
) -> TaskResult[AtelierRunResult]:
    """Multi-run (N=3, seuil ≥2/3) — variance du juge Mistral Small.

    Agit-puis-mort : aucune alerte attendue (ordre chronologique normal).
    Joué 3 fois en série ; vert si ≥2 passes n'émettent pas d'alerte."""
    return await run_atelier_multirun_case(
        driver,
        CHECK_ACT_THEN_DEATH_INPUTS,
        n=3,
        check=_check_act_then_death,
    )
