"""Session protest unifiée pour tous les evals Felix.

Run:
    protest eval evals.session:session
    protest eval evals.session:session --tag pipeline
    protest eval evals.session:session --tag ingest
    protest eval evals.session:session --tag chatbot
    protest eval evals.session:session --last-failed
    protest eval evals.session:session -n 4
    protest history --evals --show
    protest history --evals --compare
"""

from __future__ import annotations

import os

from protest import ProTestSession
from protest.evals import ModelInfo

from evals.chatbot.dataset import CHATBOT_DATASET
from evals.ingest.dataset import INGEST_DATASET
from evals.ingest.task import analyze_scene_task
from evals.pipeline.dataset import PIPELINE_DATASET
from evals.pipeline.tasks import unified_pipeline, unified_pipeline_task
from evals.task import felix_task

from felix.config import settings

session = ProTestSession(history=True)
_pipeline_model = os.environ.get("FLX_EVAL_MODEL", settings.llm_model)
_chat_model = settings.llm_chat_model or _pipeline_model
_model_label = _pipeline_model if _pipeline_model == _chat_model else f"{_pipeline_model} + {_chat_model}"

session.configure_evals(
    model=ModelInfo(
        name=_model_label,
        provider=os.environ.get("FLX_EVAL_BASE_URL") or settings.llm_base_url or "mistral-api",
    )
)

session.bind(unified_pipeline)
session.add_eval_suite(PIPELINE_DATASET, task=unified_pipeline_task, tags=["pipeline"])
session.add_eval_suite(INGEST_DATASET, task=analyze_scene_task, tags=["ingest"])
session.add_eval_suite(CHATBOT_DATASET, task=felix_task, tags=["chatbot"])
