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
    Neo4jDriver,
    RelationAgentsDep,
)
from felix.api.models import ChatRequest
from felix.atelier.agent import ATELIER_CHOICES, DEFAULT_PROFILE
from felix.core import GenericDeps, consistency_check

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


@router.get("/profiles")
async def atelier_profiles() -> list[dict[str, str]]:
    """Modes proposés par le sélecteur de l'UI (clé + libellé)."""
    return [{"key": c.key, "label": c.label} for c in ATELIER_CHOICES.values()]


@router.post("/chat")
async def atelier_chat(
    body: ChatRequest,
    agents: AtelierAgentsDep,
    relation_agents: RelationAgentsDep,
    chronicle_agents: ChronicleAgentsDep,
    driver: Neo4jDriver,
) -> EventSourceResponse:
    choice = ATELIER_CHOICES.get(body.profile, ATELIER_CHOICES[DEFAULT_PROFILE])
    agent = agents[choice.key]
    relation_agent = relation_agents[choice.key]
    chronicle_agent = chronicle_agents[choice.key]
    deps = GenericDeps(driver=driver, profile=choice.profile)

    message_history = None
    if body.message_history:
        message_history = ModelMessagesTypeAdapter.validate_python(body.message_history)

    async def stream_pass(
        sub_agent: Agent, history: list | None, *, stream_text: bool, holder: dict
    ) -> AsyncGenerator[ServerSentEvent]:
        """Joue une passe via `.iter()` : draine les cartes des tools EN LIVE (à
        chaque node) et, si `stream_text`, streame le texte. Stocke `usage` +
        `messages` dans `holder` (un générateur ne peut pas « return »). Factorisé
        pour les 3 passes : entités (texte streamé) ; relieur/chroniqueur (cartes
        live, pas de texte → une seule bulle). `deps`/`body.message` capturés."""
        async with sub_agent.iter(
            body.message, deps=deps, message_history=history
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

    async def event_generator() -> AsyncGenerator[ServerSentEvent]:
        try:
            # Passe 1 « entités » : texte streamé + cartes live.
            yield ServerSentEvent(data="Felix écrit…", event="phase")
            main: dict = {}
            async for ev in stream_pass(agent, message_history, stream_text=True, holder=main):
                yield ev

            # Passe 2 « relieur » puis passe 3 « chroniqueur » : cartes EN LIVE,
            # pas de texte (une seule bulle), un marqueur `phase` par passe. Le
            # chroniqueur tourne SANS historique (sinon il re-chronique les tours
            # passés → doublons ; il relit les entités du graphe).
            extra_usages = []
            for sub_agent, label, hist, phase_text in (
                (relation_agent, "relations", message_history, "Felix relie les fiches…"),
                (chronicle_agent, "événements", None, "Felix note les événements…"),
            ):
                try:
                    yield ServerSentEvent(data=phase_text, event="phase")
                    sub: dict = {}
                    async for ev in stream_pass(sub_agent, hist, stream_text=False, holder=sub):
                        yield ev
                    extra_usages.append(sub["usage"])
                except Exception:
                    logger.exception("passe %s échouée (tour non bloqué)", label)

            usages = [main["usage"], *extra_usages]
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

            serialized = ModelMessagesTypeAdapter.dump_python(main["messages"], mode="json")
            yield ServerSentEvent(data=json.dumps(serialized), event="history")

            # Check de cohérence (sur deps.check_candidates seulement). Best-effort :
            # isolé pour qu'une panne du juge n'empêche jamais le `done`.
            yield ServerSentEvent(data="Felix vérifie la cohérence…", event="phase")
            try:
                async for alert in _consistency_alerts(driver, deps, choice.profile):
                    yield alert
            except Exception:
                logger.exception("consistency_check a échoué (tour non bloqué)")

            yield ServerSentEvent(data="", event="done")
        except Exception as e:
            yield ServerSentEvent(data=str(e), event="error")

    return EventSourceResponse(event_generator())
