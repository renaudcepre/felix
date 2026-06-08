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
    seen: set[str] = set()
    for touched in deps.touched_ids:
        verdict = await consistency_check(driver, touched, deps.write_log, profile)
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

    def drain_cards() -> list[ServerSentEvent]:
        events = [
            ServerSentEvent(data=card.model_dump_json(), event="tool")
            for card in deps.ui_events
        ]
        deps.ui_events.clear()
        return events

    async def event_generator() -> AsyncGenerator[ServerSentEvent]:
        try:
            async with agent.iter(
                body.message, deps=deps, message_history=message_history
            ) as run:
                async for node in run:
                    # Cartes poussées par les tools du node précédent (CallToolsNode).
                    for event in drain_cards():
                        yield event
                    if Agent.is_model_request_node(node):
                        async with node.stream(run.ctx) as request_stream:
                            async for text in request_stream.stream_text(delta=True):
                                yield ServerSentEvent(data=text, event="text")
                for event in drain_cards():
                    yield event

                # 2e passe « relieur » (relations lâchées en fin de tour) puis 3e
                # passe « chroniqueur » (événements ordonnés du beat). Toutes deux
                # NON streamées — on ne lit jamais leur output et on n'émet aucun
                # `text` → une seule bulle ; leurs cartes sortent via deps.ui_events.
                # Contexte = historique d'AVANT ce tour ; les entités du beat sont
                # relues du graphe (list_entities).
                extra_usages = []
                for sub_agent, label in (
                    (relation_agent, "relations"),
                    (chronicle_agent, "événements"),
                ):
                    try:
                        sub = await sub_agent.run(
                            body.message, deps=deps, message_history=message_history
                        )
                        extra_usages.append(sub.usage())
                        for event in drain_cards():
                            yield event
                    except Exception:
                        logger.exception("passe %s échouée (tour non bloqué)", label)

                usages = [run.usage(), *extra_usages]
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

                serialized = ModelMessagesTypeAdapter.dump_python(
                    run.all_messages(), mode="json"
                )
                yield ServerSentEvent(data=json.dumps(serialized), event="history")

                # Check de cohérence sur les entités touchées ce tour. Best-effort :
                # isolé dans un try/except pour qu'une panne du judge n'empêche
                # jamais l'événement `done`.
                try:
                    async for alert in _consistency_alerts(driver, deps, choice.profile):
                        yield alert
                except Exception:
                    logger.exception("consistency_check a échoué (tour non bloqué)")

                yield ServerSentEvent(data="", event="done")
        except Exception as e:
            yield ServerSentEvent(data=str(e), event="error")

    return EventSourceResponse(event_generator())
