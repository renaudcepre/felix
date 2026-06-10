"""Route SSE du bot B (atelier) — texte streamé + cartes tool structurées.

Protocole d'événements (aligné sur le modèle AtelierMsg du front) :
- ``text``    : delta de texte du modèle
- ``tool``    : carte structurée émise par un tool (JSON ToolCard)
- ``usage``   : tokens de la requête (JSON)
- ``history`` : message_history sérialisé pour le tour suivant (JSON)
- ``alert``   : incohérence détectée par le check de cohérence (JSON, kind=alert)
- ``done`` / ``error``
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessagesTypeAdapter
from sse_starlette import EventSourceResponse, ServerSentEvent

from felix.api.deps import (
    AtelierAgentsDep,
    ChronicleAgentsDep,
    GateAgentDep,
    MasterAgentsDep,
    Neo4jDriver,
    RelationAgentsDep,
)
from felix.api.history import window_history_by_tokens
from felix.api.models import ChatRequest
from felix.atelier.agent import ATELIER_CHOICES, DEFAULT_PROFILE
from felix.config import settings
from felix.core import (
    GenericDeps,
    consistency_check,
    consume_unnotified_edits,
    recent_entities,
    recent_user_edits,
    render_recent_block,
    render_user_edits_block,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

    from felix.core import Profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/atelier", tags=["atelier"])


async def _consistency_alerts(
    driver: AsyncDriver, deps: GenericDeps, profile: Profile | None
) -> AsyncGenerator[ServerSentEvent]:
    """Carte `alert` par contradiction DISTINCTE sur les entités touchées ce tour.

    Dédupliqué : une même incohérence remonte souvent de plusieurs entités voisines
    (voisinages qui se recouvrent) → une seule carte par tour. `message` = phrase
    courte pour l'auteur ; `reason` (brouillon du judge) sert de filet de secours.
    """
    # On ne juge QUE les entités où une contradiction est possible ce tour
    # (relation / événement / valeur écrasée — cf. deps.check_candidates), pas
    # chaque entité touchée : un juge par entité touchée = ~20-30 appels/tour. Les
    # checks prouvés (temporel, spatial) sont tous portés par une relation ou un
    # événement → couverts. Et on lance les juges EN PARALLÈLE (gather) : le blanc
    # de fin de tour passe de Σ(appels) à max(appels) — Small encaisse (5M tok/min).
    ids = list(deps.check_candidates)
    if not ids:
        return
    verdicts = await asyncio.gather(
        *(consistency_check(driver, i, deps.write_log, profile) for i in ids),
        return_exceptions=True,
    )
    seen: set[str] = set()
    for verdict in verdicts:
        if isinstance(verdict, BaseException):
            logger.warning("un check a échoué (ignoré) : %r", verdict)
            continue
        if not verdict.contradiction:
            continue
        alert_body = verdict.message.strip() or verdict.reason
        key = alert_body.lower()
        if key in seen:
            continue
        seen.add(key)
        yield ServerSentEvent(
            data=json.dumps({
                "kind": "alert",
                "title": "Incohérence possible",
                "body": alert_body,
                "status": "open",
            }),
            event="alert",
        )


async def _stream_pass(  # noqa: PLR0913 — une passe = agent + prompt + historique + deps partagés
    sub_agent: Agent, prompt: str, history: list | None, deps: GenericDeps,
    *, stream_text: bool, holder: dict
) -> AsyncGenerator[ServerSentEvent]:
    """Joue une passe via `.iter()` : draine les cartes des tools EN LIVE (à
    chaque node) et, si `stream_text`, streame le texte. Stocke `usage` +
    `messages` dans `holder` (un générateur ne peut pas « return »). Factorisé
    pour les 4 passes : maître (texte streamé) ; extracteurs (cartes live, pas
    de texte → une seule bulle). `prompt` varie : message nu pour le maître et
    le chroniqueur, message préfixé du working set pour entités/relieur."""
    async with sub_agent.iter(
        prompt, deps=deps, message_history=history
    ) as run:
        async for node in run:
            for card in deps.ui_events:
                yield ServerSentEvent(data=card.model_dump_json(), event="tool")
            deps.ui_events.clear()
            if stream_text and Agent.is_model_request_node(node):
                async with node.stream(run.ctx) as request_stream:
                    async for text in request_stream.stream_text(delta=True):
                        yield ServerSentEvent(data=text, event="text")
        for card in deps.ui_events:
            yield ServerSentEvent(data=card.model_dump_json(), event="tool")
        deps.ui_events.clear()
        holder["usage"] = run.usage()
        holder["messages"] = run.all_messages()


async def _master_prompt(driver: AsyncDriver, message: str) -> str:
    """Préfixe le message du maître des actions manuelles PAS ENCORE annoncées
    (#61). Une fois suffit : le fil threadé retient — répéter le bloc chaque tour
    ne ferait que gonfler l'historique. Les extracteurs, eux, stateless, reçoivent
    le bloc COMPLET à chaque tour d'extraction (cf. event_generator)."""
    block = render_user_edits_block(await consume_unnotified_edits(driver))
    return f"{block}\n\n{message}" if block else message


async def _apply_gate_verdict(gate_task: asyncio.Task, deps: GenericDeps, usages: list) -> None:
    """Attend le gate et pose `extraction_requested`. Best-effort FAIL-CLOSED : si le
    gate crashe (transient LLM), on n'extrait pas ce tour — l'invariant produit n°1
    reste « jamais d'écriture sans contenu », et le fait peut être redonné."""
    try:
        gate_run = await gate_task
        usages.append(gate_run.usage())
        if gate_run.output.noter:
            deps.extraction_requested = True
            deps.write_log.append(
                f"contenu signalé pour extraction : {gate_run.output.fait.strip()}"
            )
    except Exception:
        logger.exception("gate de routage échoué (tour sans extraction)")


@router.get("/profiles")
async def atelier_profiles() -> list[dict[str, str]]:
    """Modes proposés par le sélecteur de l'UI (clé + libellé)."""
    return [{"key": c.key, "label": c.label} for c in ATELIER_CHOICES.values()]


@router.post("/chat")
async def atelier_chat(  # noqa: PLR0913 — params = injection de dépendances FastAPI
    body: ChatRequest,
    gate_agent: GateAgentDep,
    master_agents: MasterAgentsDep,
    agents: AtelierAgentsDep,
    relation_agents: RelationAgentsDep,
    chronicle_agents: ChronicleAgentsDep,
    driver: Neo4jDriver,
) -> EventSourceResponse:
    choice = ATELIER_CHOICES.get(body.profile, ATELIER_CHOICES[DEFAULT_PROFILE])
    master_agent = master_agents[choice.key]
    agent = agents[choice.key]
    relation_agent = relation_agents[choice.key]
    chronicle_agent = chronicle_agents[choice.key]
    deps = GenericDeps(driver=driver, profile=choice.profile)

    message_history = None
    if body.message_history:
        full = ModelMessagesTypeAdapter.validate_python(body.message_history)
        # Borne l'historique threadé par budget de tokens : on garde les tours
        # récents, le graphe (list_entities/find_entity) sert de mémoire longue.
        # Au niveau route plutôt que via history_processors → borne AUSSI le payload
        # SSE `history` renvoyé au front (réseau + mémoire front), pas que l'input modèle.
        message_history = window_history_by_tokens(full, settings.history_token_budget)

    async def event_generator() -> AsyncGenerator[ServerSentEvent]:
        # GATE de routage STATELESS : décide si ce tour doit extraire, sur le message
        # SEUL (jamais le fil → l'ornière d'auto-imitation est impossible par
        # construction, issue #43). Lancé EN PARALLÈLE du maître : sa latence est
        # masquée par le stream de la réponse, on l'attend juste avant le dispatch.
        gate_task = asyncio.create_task(gate_agent.run(body.message))
        try:
            # Passe 0 « maître » : MÈNE la conversation (texte streamé), threadée.
            # La décision d'extraire ne lui appartient plus (cf. gate ci-dessus).
            yield ServerSentEvent(data="Felix répond…", event="phase")
            master: dict = {}
            async for ev in _stream_pass(
                master_agent, await _master_prompt(driver, body.message),
                message_history, deps, stream_text=True, holder=master
            ):
                yield ev

            usages = [master["usage"]]
            await _apply_gate_verdict(gate_task, deps, usages)

            # Extracteurs MUETS, dispatchés UNIQUEMENT si le gate a signalé du contenu.
            # Une salutation / une question n'écrit donc RIEN (hallu impossible par
            # construction, tour conversationnel moins cher). Ordre : entités → relieur →
            # chroniqueur (ce dernier SANS historique, sinon re-chronique → doublons).
            if deps.extraction_requested:
                # Working set injecté EN CODE en tête du prompt des passes entités/
                # relieur : les N entités récemment actives (borné, pas toute la base).
                # Sans lui, l'extracteur ne relit pas la base avant d'écrire et crée
                # un doublon au baptême (« le mage noir se nomme X » → fiche X neuve,
                # bug Adator). Le chroniqueur garde le message nu (il ne crée pas).
                block = render_recent_block(
                    await recent_entities(driver, settings.recent_entities_limit)
                )
                # Décisions manuelles de l'auteur (#61) : injectées à CHAQUE tour
                # d'extraction tant que le tombstone vit (TTL) — c'est la garantie
                # qu'une fiche supprimée depuis l'UI ne renaît pas via l'historique.
                edits_block = render_user_edits_block(await recent_user_edits(
                    driver, settings.user_edits_limit, settings.user_edits_ttl_minutes
                ))
                extract_prompt = "\n\n".join(
                    part for part in (edits_block, block, body.message) if part
                )
                for sub_agent, label, prompt, hist, phase_text in (
                    (agent, "entités", extract_prompt, message_history,
                     "Felix met à jour la bible…"),
                    (relation_agent, "relations", extract_prompt, message_history,
                     "Felix relie les fiches…"),
                    (chronicle_agent, "événements", body.message, None,
                     "Felix note les événements…"),
                ):
                    try:
                        yield ServerSentEvent(data=phase_text, event="phase")
                        sub: dict = {}
                        async for ev in _stream_pass(
                            sub_agent, prompt, hist, deps, stream_text=False, holder=sub
                        ):
                            yield ev
                        usages.append(sub["usage"])
                    except Exception:
                        logger.exception("passe %s échouée (tour non bloqué)", label)

                # Check de cohérence (sur deps.check_candidates) — seulement si on a
                # extrait. Best-effort, isolé pour ne jamais bloquer le `done`.
                yield ServerSentEvent(data="Felix vérifie la cohérence…", event="phase")
                try:
                    async for alert in _consistency_alerts(driver, deps, choice.profile):
                        yield alert
                except Exception:
                    logger.exception("consistency_check a échoué (tour non bloqué)")

            yield ServerSentEvent(
                data=json.dumps(
                    {
                        "request_tokens": sum(u.request_tokens or 0 for u in usages),
                        "response_tokens": sum(u.response_tokens or 0 for u in usages),
                        "total_tokens": sum(u.total_tokens or 0 for u in usages),
                    }
                ),
                event="usage",
            )

            # L'historique threadé = le FIL DU MAÎTRE (la conversation), pas les
            # tool-calls d'extraction : le graphe est la mémoire longue, relue à la
            # demande. Plus léger, et la conversation reste cohérente d'un tour à l'autre.
            serialized = ModelMessagesTypeAdapter.dump_python(master["messages"], mode="json")
            yield ServerSentEvent(data=json.dumps(serialized), event="history")

            yield ServerSentEvent(data="", event="done")
        except Exception as e:
            gate_task.cancel()
            yield ServerSentEvent(data=str(e), event="error")

    return EventSourceResponse(event_generator())
