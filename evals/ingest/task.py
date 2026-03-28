"""Ingest eval task with protest fixture-based setup."""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from protest import Use, fixture

from felix.ingest.analyzer import AnalyzerAgents, analyze_scene, create_analyzer_agent

if TYPE_CHECKING:
    from felix.ingest.models import SceneAnalysis

import functools

SCENES_DIR = Path(__file__).parent.parent.parent / "data" / "scenes"


@fixture()
def analyzer_agents() -> AnalyzerAgents:
    """Create analyzer agents once, shared across all ingest cases."""
    model_name = os.environ.get("FLX_EVAL_MODEL")
    base_url = os.environ.get("FLX_EVAL_BASE_URL") or None
    return create_analyzer_agent(model_name, base_url)


@functools.cache
def _load_scene(filename: str) -> str:
    return (SCENES_DIR / filename).read_text(encoding="utf-8")


async def analyze_scene_task(
    scene_filename: str,
    agents: Annotated[AnalyzerAgents, Use(analyzer_agents)],
) -> SceneAnalysis:
    scene_text = _load_scene(scene_filename)
    return await analyze_scene(agents, scene_text)
