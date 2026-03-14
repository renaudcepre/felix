"""Task function wrapping the Felix agent for pydantic-evals."""

from __future__ import annotations

import os

import chromadb

from felix.agent.chat_agent import create_agent
from felix.agent.deps import FelixDeps
from felix.db.schema import init_db
from felix.db.seed import seed_db
from felix.vectorstore.seed import seed_scenes

_deps: FelixDeps | None = None


async def _get_deps() -> FelixDeps:
    global _deps  # noqa: PLW0603
    if _deps is not None:
        return _deps

    db = await init_db(":memory:")
    await seed_db(db)

    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(name="scenes_eval")
    seed_scenes(collection)

    _deps = FelixDeps(db=db, chroma_collection=collection)
    return _deps


async def felix_task(question: str) -> str:
    deps = await _get_deps()
    model_name = os.environ.get("FELIX_EVAL_MODEL")
    base_url = os.environ.get("FELIX_EVAL_BASE_URL")
    agent = create_agent(model_name, base_url)
    result = await agent.run(question, deps=deps)
    return result.output
