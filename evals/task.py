"""Chatbot eval task with protest fixture-based setup."""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import chromadb
from protest import Use, console, fixture

from felix.agent.chat_agent import create_agent
from felix.agent.deps import FelixDeps
from felix.graph.driver import get_driver, setup_constraints
from felix.graph.seed import seed_graph
from felix.vectorstore.seed import seed_scenes

if TYPE_CHECKING:
    pass


@fixture()
async def felix_deps() -> FelixDeps:
    """Seed graph + vectorstore once, shared across all chatbot cases."""
    console.print("[dim]chatbot:[/] seeding graph...")
    driver = get_driver()
    await setup_constraints(driver)
    await seed_graph(driver)

    console.print("[dim]chatbot:[/] seeding vectorstore...")
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(name="scenes_eval")
    seed_scenes(collection)

    console.print("[green]chatbot:[/] ready")
    return FelixDeps(driver=driver, chroma_collection=collection)


async def felix_task(
    question: str,
    deps: Annotated[FelixDeps, Use(felix_deps)],
) -> str:
    agent = create_agent()
    result = await agent.run(question, deps=deps)
    return result.output
