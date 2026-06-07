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
from evals.atelier.dataset import atelier_cases

# Import runtime (pas TYPE_CHECKING) : protest résout les annotations des evals
# via get_type_hints — `TaskResult[AtelierRunResult]` doit être évaluable.
from evals.atelier.task import AtelierRunResult, atelier_driver, run_atelier_case
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
