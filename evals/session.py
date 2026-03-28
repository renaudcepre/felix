"""Session protest unifiée pour tous les evals Felix.

Run:
    protest eval evals.session:session
    protest eval evals.session:session --tag pipeline
    protest eval evals.session:session --tag chatbot
    protest eval evals.session:session -n 4
    protest history --runs
"""
from __future__ import annotations

import os

from protest import ProTestSession
from protest.evals import ModelInfo

from evals.chatbot.dataset import CHATBOT_DATASET
from evals.ingest.dataset import INGEST_DATASET
from evals.ingest.task import analyzer_agents, analyze_scene_task
from evals.pipeline.dataset import PIPELINE_DATASET
from evals.pipeline.tasks import unified_pipeline, unified_pipeline_task
from evals.task import felix_deps, felix_task
from felix.config import settings

pipeline_model = ModelInfo(name=os.environ.get("FLX_EVAL_MODEL", settings.llm_model))
chat_model = ModelInfo(name=settings.llm_chat_model or settings.llm_model)

session = ProTestSession(history=True)
session.configure_evals(model=pipeline_model)

session.bind(unified_pipeline)
session.bind(analyzer_agents)
session.bind(felix_deps)
session.add_eval_suite(PIPELINE_DATASET, task=unified_pipeline_task, model=pipeline_model, tags=["pipeline"])
session.add_eval_suite(INGEST_DATASET, task=analyze_scene_task, model=pipeline_model, tags=["ingest"])
session.add_eval_suite(CHATBOT_DATASET, task=felix_task, model=chat_model, tags=["chatbot"])
