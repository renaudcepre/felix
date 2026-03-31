"""Session protest pour les evals Felix.

Run:
    protest eval evals.session:session
    protest eval evals.session:session --tag pipeline
    protest eval evals.session:session --tag chatbot
    protest eval evals.session:session -n 4
    protest history --runs
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Annotated

from pydantic_ai import Agent
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.providers.mistral import MistralProvider
from protest import From, Use
from protest.evals import EvalCase, EvalSession, JudgeResponse, ModelInfo

from evals.chatbot.dataset import chatbot_cases
from evals.evaluators import contains_expected_facts
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

    from felix.agent.deps import FelixDeps
    from felix.ingest.analyzer import AnalyzerAgents
    from felix.ingest.models import SceneAnalysis
    from evals.pipeline.task import PipelineQueryResult

pipeline_model = ModelInfo(name=os.environ.get("FLX_EVAL_MODEL", settings.llm_model))
chat_model = ModelInfo(name=settings.llm_chat_model or settings.llm_model)


class FelixJudge:
    name = "mistral-small-latest"
    provider = "mistral"

    async def judge(self, prompt: str, output_type: type) -> JudgeResponse:
        model = MistralModel(
            "mistral-small-latest",
            provider=MistralProvider(api_key=settings.llm_api_key),
        )
        agent = Agent(model, output_type=output_type)
        result = await agent.run(prompt)
        usage = result.usage()
        return JudgeResponse(
            output=result.output,
            input_tokens=usage.request_tokens,
            output_tokens=usage.response_tokens,
        )


session = EvalSession(model=pipeline_model, judge=FelixJudge())

session.bind(unified_pipeline)
session.bind(analyzer_agents)
session.bind(felix_deps)


@session.eval()
async def pipeline(
    case: Annotated[EvalCase, From(pipeline_cases)],
    driver: Annotated[AsyncDriver, Use(unified_pipeline)],
) -> PipelineQueryResult:
    return await _query(driver, case.inputs)


@session.eval()
async def ingest(
    case: Annotated[EvalCase, From(ingest_cases)],
    agents: Annotated[AnalyzerAgents, Use(analyzer_agents)],
) -> SceneAnalysis:
    return await analyze_scene(agents, _load_scene(case.inputs))


@session.eval(model=chat_model)
async def chatbot(
    case: Annotated[EvalCase, From(chatbot_cases)],
    deps: Annotated[FelixDeps, Use(felix_deps)],
) -> str:
    agent = create_agent()
    result = await agent.run(case.inputs, deps=deps)
    return result.output
