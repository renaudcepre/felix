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
from evals.pipeline.tasks import unified_pipeline_task
from evals.task import felix_task

session = ProTestSession(history=True)
session.configure_evals(
    model=ModelInfo(
        name=os.environ.get("FLX_EVAL_MODEL", "unknown"),
        provider=os.environ.get("FLX_EVAL_BASE_URL", "mistral-api"),
    )
)

session.register_dataset(PIPELINE_DATASET, task=unified_pipeline_task, tags=["pipeline"])
session.register_dataset(INGEST_DATASET, task=analyze_scene_task, tags=["ingest"])
session.register_dataset(CHATBOT_DATASET, task=felix_task, tags=["chatbot"])
