"""Task d'eval du bot atelier : wipe + seed du graphe, run agent, lecture du graphe.

Chaque cas part d'un graphe Neo4j dans un état connu (vide ou seedé avec les
personnages du cas) et le résultat expose TOUT ce que les evaluators jugent :
la réponse, l'état du graphe après le run, et les cartes UI émises par les tools.

ATTENTION : le wipe est global (MATCH (n) DETACH DELETE n) — même base que le
dev local, comme `just db-clean`. Un lock sérialise les cas entre eux, mais ne
pas lancer cette session en même temps que la session legacy.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from protest import fixture
from protest.evals import TaskResult

from evals._judge import MISTRAL_SMALL_INPUT_COST, MISTRAL_SMALL_OUTPUT_COST
from felix.atelier.agent import create_atelier_agent
from felix.atelier.deps import AtelierDeps
from felix.graph.driver import get_driver, setup_constraints
from felix.graph.repositories import create_character, list_all_characters_full
from felix.ingest.resolver import slugify

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# Les cas wipent/écrivent la même base → sérialisés même sous -n 4.
_GRAPH_LOCK = asyncio.Lock()


@dataclass
class AtelierRunResult:
    """Sortie d'un cas : réponse + état du graphe + cartes tool émises."""

    answer: str
    characters: list[dict[str, Any]] = field(default_factory=list)
    cards: list[dict[str, str]] = field(default_factory=list)


@fixture()
async def atelier_driver() -> AsyncDriver:
    driver = get_driver()
    await setup_constraints(driver)
    return driver


async def _wipe_graph(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")


async def _seed_characters(driver: AsyncDriver, seed: list[dict[str, str]]) -> None:
    for char in seed:
        await create_character(
            driver, slugify(char["name"]), char["name"], char.get("background")
        )


async def run_atelier_case(
    driver: AsyncDriver, inputs: dict[str, Any]
) -> TaskResult[AtelierRunResult]:
    async with _GRAPH_LOCK:
        await _wipe_graph(driver)
        await _seed_characters(driver, inputs.get("seed", []))

        deps = AtelierDeps(driver=driver)
        agent = create_atelier_agent()
        result = await agent.run(inputs["message"], deps=deps)

        characters = await list_all_characters_full(driver)

    usage = result.usage()
    in_tok, out_tok = usage.request_tokens or 0, usage.response_tokens or 0
    return TaskResult(
        output=AtelierRunResult(
            answer=result.output,
            characters=[dict(c) for c in characters],
            cards=[card.model_dump() for card in deps.ui_events],
        ),
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost=in_tok * MISTRAL_SMALL_INPUT_COST + out_tok * MISTRAL_SMALL_OUTPUT_COST,
    )
