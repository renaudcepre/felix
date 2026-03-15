"""Task function wrapping the scene analyzer for pydantic-evals."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from felix.ingest.analyzer import create_analyzer_agent

if TYPE_CHECKING:
    from felix.ingest.models import SceneAnalysis

_agent = None
_scenes_cache: dict[str, str] = {}

SCENES_DIR = Path(__file__).parent.parent.parent / "data" / "scenes"


def _get_agent():
    global _agent  # noqa: PLW0603
    if _agent is not None:
        return _agent
    model_name = os.environ.get("FLX_EVAL_MODEL")
    base_url = os.environ.get("FLX_EVAL_BASE_URL")
    _agent = create_analyzer_agent(model_name, base_url)
    return _agent


def _load_scene(filename: str) -> str:
    if filename not in _scenes_cache:
        _scenes_cache[filename] = (SCENES_DIR / filename).read_text(encoding="utf-8")
    return _scenes_cache[filename]


async def analyze_scene_task(scene_filename: str) -> SceneAnalysis:
    agent = _get_agent()
    scene_text = _load_scene(scene_filename)
    result = await agent.run(scene_text)
    return result.output
