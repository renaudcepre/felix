"""Session protest pour les evals Felix.

Run:
    protest eval evals.session:session
    protest eval evals.session:session::pipeline
    protest eval evals.session:session::chatbot
    protest eval evals.session:session -n 4
    protest history --runs
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Annotated

from protest import From, ProTestSession, Use
from protest.evals import EvalCase, EvalSuite, ModelLabel, TaskResult

from evals._judge import FelixJudge
from evals.chatbot.dataset import chatbot_cases
from evals.ingest.dataset import ingest_cases
from evals.ingest.task import _load_scene, analyzer_agents
from evals.pipeline.dataset import pipeline_cases
from evals.pipeline.task import _query
from evals.pipeline.tasks import unified_pipeline
from evals.task import felix_deps
from felix.agent.chat_agent import create_agent
from felix.config import settings
from felix.ingest.analyzer import analyze_scene

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from evals.pipeline.task import PipelineQueryResult
    from felix.agent.deps import FelixDeps
    from felix.ingest.analyzer import AnalyzerAgents
    from felix.ingest.models import SceneAnalysis

pipeline_model = ModelLabel(name=os.environ.get("FLX_EVAL_MODEL", settings.llm_model), provider="together")
chat_model = ModelLabel(name=settings.llm_chat_model or settings.llm_model, provider="openrouter")


session = ProTestSession(history=True)

session.bind(unified_pipeline)
session.bind(analyzer_agents)
session.bind(felix_deps)

judge = FelixJudge()
pipeline_suite = EvalSuite("pipeline", model=pipeline_model, judge=judge)
ingest_suite = EvalSuite("ingest", model=pipeline_model, judge=judge)
chatbot_suite = EvalSuite("chatbot", model=chat_model, judge=judge)

session.add_suite(pipeline_suite)
session.add_suite(ingest_suite)
session.add_suite(chatbot_suite)


@pipeline_suite.eval()
async def pipeline(
    case: Annotated[EvalCase, From(pipeline_cases)],
    driver: Annotated[AsyncDriver, Use(unified_pipeline)],
) -> PipelineQueryResult:
    return await _query(driver, case.inputs)


@ingest_suite.eval()
async def ingest(
    case: Annotated[EvalCase, From(ingest_cases)],
    agents: Annotated[AnalyzerAgents, Use(analyzer_agents)],
) -> SceneAnalysis:
    return await analyze_scene(agents, _load_scene(case.inputs))


@chatbot_suite.eval()
async def chatbot(
    case: Annotated[EvalCase, From(chatbot_cases)],
    deps: Annotated[FelixDeps, Use(felix_deps)],
) -> TaskResult[str]:
    agent = create_agent()
    result = await agent.run(case.inputs, deps=deps)
    usage = result.usage()
    in_tok, out_tok = usage.request_tokens or 0, usage.response_tokens or 0
    return TaskResult(
        output=result.output,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost=in_tok * 0.10 / 1e6 + out_tok * 0.30 / 1e6,
    )
