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
from felix.atelier.agent import create_atelier_agent, create_relation_agent
from felix.atelier.deps import AtelierDeps
from felix.core import SCENARIO_PROFILE, all_entities, all_relations, consistency_check
from felix.graph.driver import get_driver, setup_constraints
from felix.ingest.resolver import slugify

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# Les cas wipent/écrivent la même base → sérialisés même sous -n 4.
_GRAPH_LOCK = asyncio.Lock()


@dataclass
class AtelierRunResult:
    """Sortie d'un cas : réponse + état du graphe + cartes tool + verdict du check."""

    answer: str
    characters: list[dict[str, Any]] = field(default_factory=list)
    cards: list[dict[str, str]] = field(default_factory=list)
    # Graphe complet (tous types, + relations) pour les cas scénario multi-beats :
    # recall d'entités, résolution (entité unique sur plusieurs tours), relations.
    entities: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    # Verdict du consistency_check rejoué quand le cas demande "check" (la route
    # SSE émet une alerte ssi contradiction est True) ; None sinon.
    alert: dict[str, Any] | None = None


@fixture()
async def atelier_driver() -> AsyncDriver:
    driver = get_driver()
    await setup_constraints(driver)
    return driver


async def _wipe_graph(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")


async def _seed_entities(driver: AsyncDriver, seed: list[dict[str, Any]]) -> None:
    """Seed d'entités :GenEntity — même monde que le bot B promu (plus de :Character).

    Compat : {'name', 'background'?} = personnage. Forme étendue {'name',
    'entity_type', 'props'} pour seeder un lieu/objet (cas du check)."""
    async with driver.session() as session:
        for e in seed:
            etype = e.get("entity_type", "personnage")
            props = dict(e.get("props", {}))
            if e.get("background"):
                props.setdefault("background", e["background"])
            await session.run(
                "MERGE (x:GenEntity {id: $id})"
                " SET x.name = $name, x.entity_type = $type, x += $props",
                id=slugify(e["name"]), name=e["name"], type=etype, props=props,
            )


async def run_atelier_case(
    driver: AsyncDriver, inputs: dict[str, Any]
) -> TaskResult[AtelierRunResult]:
    async with _GRAPH_LOCK:
        await _wipe_graph(driver)
        await _seed_entities(driver, inputs.get("seed", []))

        agent = create_atelier_agent()
        relation_agent = create_relation_agent()
        # Un cas est soit mono-tour ("message"), soit multi-beats ("beats") joués
        # en séquence sur le MÊME graphe, l'historique threadé tour à tour (comme
        # une vraie conversation : teste l'extraction cumulative + la résolution).
        # Chaque beat = 2 passes sur le MÊME deps : agent d'entités, puis relieur
        # dédié (récupère les relations lâchées en fin de tour mono-passe).
        beats = inputs.get("beats") or [inputs["message"]]
        history = None
        cards: list[Any] = []
        in_tok = out_tok = 0
        deps = result = None
        for beat in beats:
            prev = history  # historique d'AVANT ce beat (Option B, partagé)
            deps = AtelierDeps(driver=driver, profile=SCENARIO_PROFILE)
            result = await agent.run(beat, deps=deps, message_history=prev)
            rel_result = await relation_agent.run(beat, deps=deps, message_history=prev)
            history = result.all_messages()  # le tour relieur est interne/jetable
            cards.extend(deps.ui_events)
            usage, rusage = result.usage(), rel_result.usage()
            in_tok += (usage.request_tokens or 0) + (rusage.request_tokens or 0)
            out_tok += (usage.response_tokens or 0) + (rusage.response_tokens or 0)

        assert result is not None and deps is not None  # beats non vide → boucle exécutée

        entities = await all_entities(driver)
        relations = await all_relations(driver)
        # Sous-ensemble personnages : une entité « lieu » créée en passant ne doit
        # pas fausser les graph_char_count des cas mono-tour.
        characters = [
            e for e in entities
            if "personnage" in str(e.get("entity_type", "")).lower()
        ]

        # Rejoue le check de cohérence si le cas le demande (comme run_generic_case) :
        # la route SSE émet une alerte ssi le verdict conclut à une contradiction.
        alert = None
        if inputs.get("check"):
            verdict = await consistency_check(
                driver, inputs["check"], deps.write_log, SCENARIO_PROFILE
            )
            alert = verdict.model_dump()

    return TaskResult(
        output=AtelierRunResult(
            answer=result.output,
            characters=[dict(c) for c in characters],
            entities=[dict(e) for e in entities],
            relations=[dict(r) for r in relations],
            cards=[card.model_dump() for card in cards],
            alert=alert,
        ),
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost=in_tok * MISTRAL_SMALL_INPUT_COST + out_tok * MISTRAL_SMALL_OUTPUT_COST,
    )
