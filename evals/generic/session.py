"""Session protest du prototype generic-core — séparée (expérience).

Run:
    protest eval evals.generic.session:session
    just evals-generic

Wipe le graphe Neo4j partagé avant chaque cas — ne pas lancer en même temps
qu'une autre session d'evals.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from protest import From, ProTestSession, Use
from protest.evals import EvalCase, EvalSuite, ModelLabel, TaskResult

from evals._judge import FelixJudge
from evals.generic.dataset import generic_cases

# Import runtime (pas TYPE_CHECKING) : protest résout les annotations via
# get_type_hints — `TaskResult[GenericRunResult]` doit être évaluable.
from evals.generic.task import GenericRunResult, generic_driver, run_generic_case
from felix.config import settings

if TYPE_CHECKING:
    from neo4j import AsyncDriver

generic_model = ModelLabel(
    name=settings.llm_chat_model or settings.llm_model, provider="mistral"
)

session = ProTestSession(history=True)
session.bind(generic_driver)

generic_suite = EvalSuite("generic", model=generic_model, judge=FelixJudge())
session.add_suite(generic_suite)


@generic_suite.eval()
async def generic(
    case: Annotated[EvalCase, From(generic_cases)],
    driver: Annotated[AsyncDriver, Use(generic_driver)],
) -> TaskResult[GenericRunResult]:
    return await run_generic_case(driver, case.inputs)
