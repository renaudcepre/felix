"""Task d'eval du prototype générique : wipe + seed, conversation multi-tours,
dump du graphe émergent, check de cohérence optionnel.

inputs = {
    "messages": [str, ...],            # joués en séquence avec message_history
    "seed": {"entities": [...], "relations": [...]},   # état initial (optionnel)
    "check": "ref entité",             # si présent : consistency_check après le run
}

Même base Neo4j partagée que le reste — wipe global par cas, lock asyncio.
Ne pas lancer en même temps que les autres sessions d'evals.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from protest import fixture
from protest.evals import TaskResult

from evals._judge import MISTRAL_SMALL_INPUT_COST, MISTRAL_SMALL_OUTPUT_COST
from evals.generic.proto import (
    GenericDeps,
    _all_entities,
    _all_relations,
    consistency_check,
    create_generic_agent,
)
from felix.graph.driver import get_driver, setup_constraints
from felix.ingest.resolver import slugify

if TYPE_CHECKING:
    from neo4j import AsyncDriver

_GRAPH_LOCK = asyncio.Lock()


@dataclass
class GenericRunResult:
    """Sortie d'un cas : réponses + graphe émergent + cartes + verdict du check."""

    answers: list[str] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    cards: list[dict[str, str]] = field(default_factory=list)
    check: dict[str, Any] | None = None


@fixture()
async def generic_driver() -> AsyncDriver:
    driver = get_driver()
    await setup_constraints(driver)
    return driver


async def _wipe_graph(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")


async def _seed(driver: AsyncDriver, seed: dict[str, Any]) -> None:
    async with driver.session() as session:
        for e in seed.get("entities", []):
            props = dict(e.get("props", {}))
            await session.run(
                "MERGE (x:GenEntity {id: $id})"
                " SET x.name = $name, x.entity_type = $type, x += $props",
                id=slugify(e["name"]), name=e["name"],
                type=e["entity_type"], props=props,
            )
        for r in seed.get("relations", []):
            await session.run(
                """
                MATCH (a:GenEntity {id: $a}), (b:GenEntity {id: $b})
                MERGE (a)-[rel:REL {rel_type: $t}]->(b)
                """,
                a=slugify(r["from"]), b=slugify(r["to"]), t=r["rel_type"],
            )


async def run_generic_case(
    driver: AsyncDriver, inputs: dict[str, Any]
) -> TaskResult[GenericRunResult]:
    async with _GRAPH_LOCK:
        await _wipe_graph(driver)
        await _seed(driver, inputs.get("seed", {}))

        deps = GenericDeps(driver=driver)
        agent = create_generic_agent()
        out = GenericRunResult()
        in_tok = out_tok = 0

        history = None
        for message in inputs["messages"]:
            result = await agent.run(message, deps=deps, message_history=history)
            history = result.all_messages()
            out.answers.append(result.output)
            usage = result.usage()
            in_tok += usage.request_tokens or 0
            out_tok += usage.response_tokens or 0

        out.entities = await _all_entities(driver)
        out.relations = await _all_relations(driver)
        out.cards = [card.model_dump() for card in deps.ui_events]

        if inputs.get("check"):
            verdict = await consistency_check(driver, inputs["check"], deps.write_log)
            out.check = verdict.model_dump()

    return TaskResult(
        output=out,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost=in_tok * MISTRAL_SMALL_INPUT_COST + out_tok * MISTRAL_SMALL_OUTPUT_COST,
    )
