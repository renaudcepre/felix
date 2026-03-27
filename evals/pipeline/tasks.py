"""Lazy task wrappers pour les evals pipeline.

Le pattern factory de make_pipeline_task (async 0-arg → real task) n'est pas
supporté nativement par l'adapter ProTest. Ces wrappers initialisent le pipeline
une seule fois via asyncio.Lock, même en cas d'exécution parallèle (-n 4).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from evals.pipeline.task import PipelineQueryResult, make_pipeline_task

_unified_task: Callable[[str], object] | None = None
_unified_lock: asyncio.Lock | None = None


async def unified_pipeline_task(query: str) -> PipelineQueryResult:
    """Task pipeline initialisée lazily sur la fixture 'unified'."""
    global _unified_task, _unified_lock  # noqa: PLW0603
    if _unified_lock is None:
        _unified_lock = asyncio.Lock()
    async with _unified_lock:
        if _unified_task is None:
            _unified_task = await make_pipeline_task("unified")()
    return await _unified_task(query)  # type: ignore[return-value]
