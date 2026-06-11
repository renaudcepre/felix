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
from evals._utils import normalize, with_backoff
from felix.atelier.agent import (
    create_atelier_agent,
    create_chronicle_agent,
    create_relation_agent,
)
from felix.atelier.deps import AtelierDeps
from felix.config import settings
from felix.core import (
    SCENARIO_PROFILE,
    all_entities,
    all_relations,
    consistency_check,
    recent_entities,
    render_recent_block,
)
from felix.graph.driver import get_driver, setup_constraints
from felix.ingest.resolver import slugify

if TYPE_CHECKING:
    from collections.abc import Callable

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
    # Multi-run : rempli par run_atelier_multirun_case, None pour un mono-run classique.
    multirun_passes: int | None = None
    multirun_total: int | None = None


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
        chronicle_agent = create_chronicle_agent()
        # Un cas est soit mono-tour ("message"), soit multi-beats ("beats") joués
        # en séquence sur le MÊME graphe, l'historique threadé tour à tour (comme
        # une vraie conversation : teste l'extraction cumulative + la résolution).
        # Chaque beat = 3 passes sur le MÊME deps : agent d'entités, relieur
        # (relations lâchées en fin de tour), chroniqueur (événements ordonnés).
        # Toutes en Option B (historique d'AVANT le beat ; entités relues du graphe).
        beats = inputs.get("beats") or [inputs["message"]]
        history = None
        cards: list[Any] = []
        in_tok = out_tok = 0
        deps = result = None
        for beat in beats:
            prev = history  # historique d'AVANT ce beat (Option B, partagé)
            deps = AtelierDeps(driver=driver, profile=SCENARIO_PROFILE)
            # Même injection que la route : working set borné (entités récemment
            # touchées) préfixé au prompt des passes entités/relieur — sans elle le
            # harness ne testerait pas le mécanisme anti-doublon (baptême différé).
            block = render_recent_block(
                await recent_entities(driver, settings.recent_entities_limit, project=deps.project_id)
            )
            extract_beat = f"{block}\n\n{beat}" if block else beat
            result = await with_backoff(
                lambda: agent.run(extract_beat, deps=deps, message_history=prev)  # noqa: B023
            )
            rel_result = await with_backoff(
                lambda: relation_agent.run(extract_beat, deps=deps, message_history=prev)  # noqa: B023
            )
            # Chroniqueur SANS historique : il ne chronique que le beat courant (sinon
            # re-chronique les tours passés → doublons) ; entités relues du graphe.
            chr_result = await with_backoff(
                lambda: chronicle_agent.run(beat, deps=deps, message_history=None)  # noqa: B023
            )
            history = result.all_messages()  # relieur/chroniqueur internes/jetables
            cards.extend(deps.ui_events)
            for u in (result.usage(), rel_result.usage(), chr_result.usage()):
                in_tok += u.request_tokens or 0
                out_tok += u.response_tokens or 0

        assert result is not None and deps is not None  # beats non vide → boucle exécutée

        entities = await all_entities(driver, project=deps.project_id)
        relations = await all_relations(driver, project=deps.project_id)
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
            verdict = await with_backoff(
                lambda: consistency_check(driver, inputs["check"], deps.write_log, SCENARIO_PROFILE, project=deps.project_id)
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


def _check_death_then_act(result: AtelierRunResult) -> bool:
    """Mort-puis-agit : doit émettre une alerte (contradiction temporelle).

    Retourne False si le check n'a pas été exécuté (inputs sans 'check')."""
    if result.alert is None:
        return False
    return bool(result.alert.get("contradiction"))


def _check_act_then_death(result: AtelierRunResult) -> bool:
    """Agit-puis-mort : AUCUNE alerte attendue (ordre chronologique normal).

    Retourne False si le check n'a pas été exécuté (inputs sans 'check')."""
    if result.alert is None:
        return False
    return not result.alert.get("contradiction")


def _bapteme_differe_check(result: AtelierRunResult) -> bool:
    """Critères inline du cas bapteme_differe : 1 personnage, Alikazeth unique.

    Réplique graph_char_count(n=1) + entity_unique(names='Alikazeth') de façon
    autonome pour que run_atelier_multirun_case puisse compter les passes sans
    repasser par les evaluators protest."""
    if len(result.characters) != 1:
        return False
    return (
        sum(
            1
            for e in result.entities
            if normalize(str(e.get("name", ""))) == "alikazeth"
            or normalize(str(e.get("id", ""))) == "alikazeth"
        )
        == 1
    )


async def run_atelier_multirun_case(
    driver: AsyncDriver,
    inputs: dict[str, Any],
    n: int,
    check: Callable[[AtelierRunResult], bool],
) -> TaskResult[AtelierRunResult]:
    """N passes en série avec seuil majoritaire pour les cas LLM non-déterministes.

    Chaque pass repart d'un graphe vide (wipe + seed intégrés dans
    run_atelier_case). Aucune concurrence : l'API Mistral rate-limite à 429.
    Le résultat retourné est celui de la dernière pass, enrichi de
    multirun_passes et multirun_total pour le evaluator multirun_majority."""
    passes = 0
    total_in = total_out = 0
    last_tr: TaskResult[AtelierRunResult] | None = None

    for i in range(1, n + 1):
        tr = await run_atelier_case(driver, inputs)
        total_in += tr.input_tokens or 0
        total_out += tr.output_tokens or 0
        ok = check(tr.output)
        passes += ok
        status = "PASS" if ok else "FAIL"
        chars = ", ".join(str(c.get("name", "?")) for c in tr.output.characters)
        # Visible avec `just evals-atelier -s -k bapteme_differe`
        print(f"  [multirun] pass {i}/{n} → {status}  ({len(tr.output.characters)} perso(s) : {chars or '—'})")
        last_tr = tr

    assert last_tr is not None  # n >= 1 garanti par l'appelant
    last_tr.output.multirun_passes = passes
    last_tr.output.multirun_total = n
    print(f"  [multirun] verdict : {passes}/{n} passes")

    return TaskResult(
        output=last_tr.output,
        input_tokens=total_in,
        output_tokens=total_out,
        cost=total_in * MISTRAL_SMALL_INPUT_COST + total_out * MISTRAL_SMALL_OUTPUT_COST,
    )
