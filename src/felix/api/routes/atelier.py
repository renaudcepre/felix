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

from felix.api.deps import AtelierAgentsDep, Neo4jDriver, RelationAgentsDep
from felix.api.models import ChatRequest
from felix.atelier.agent import ATELIER_CHOICES, DEFAULT_PROFILE
from felix.core import GenericDeps, consistency_check

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/atelier", tags=["atelier"])


@router.get("/profiles")
async def atelier_profiles() -> list[dict[str, str]]:
    """Modes proposés par le sélecteur de l'UI (clé + libellé)."""
    return [{"key": c.key, "label": c.label} for c in ATELIER_CHOICES.values()]


@router.post("/chat")
async def atelier_chat(
    body: ChatRequest,
    agents: AtelierAgentsDep,
    relation_agents: RelationAgentsDep,
    driver: Neo4jDriver,
) -> EventSourceResponse:
    choice = ATELIER_CHOICES.get(body.profile, ATELIER_CHOICES[DEFAULT_PROFILE])
    agent = agents[choice.key]
    relation_agent = relation_agents[choice.key]
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

                # 2e passe « relieur » : crée les relations que l'agent d'entités
                # a tendance à lâcher en fin de tour. NON streamée — on ne lit
                # jamais son output et on n'émet aucun `text` → une seule bulle.
                # Contexte = historique d'AVANT ce tour (message_history) ; les
                # entités du beat sont relues via le graphe (list_entities).
                rel_usage = None
                try:
                    rel_result = await relation_agent.run(
                        body.message, deps=deps, message_history=message_history
                    )
                    rel_usage = rel_result.usage()
                    for event in drain_cards():  # cartes « Relation ajoutée »
                        yield event
                except Exception:
                    logger.exception("passe relations échouée (tour non bloqué)")

                usage = run.usage()
                yield ServerSentEvent(
                    data=json.dumps(
                        {
                            "request_tokens": (usage.request_tokens or 0)
                            + (rel_usage.request_tokens or 0 if rel_usage else 0),
                            "response_tokens": (usage.response_tokens or 0)
                            + (rel_usage.response_tokens or 0 if rel_usage else 0),
                            "total_tokens": (usage.total_tokens or 0)
                            + (rel_usage.total_tokens or 0 if rel_usage else 0),
                        }
                    ),
                    event="usage",
                )

                serialized = ModelMessagesTypeAdapter.dump_python(
                    run.all_messages(), mode="json"
                )
                yield ServerSentEvent(data=json.dumps(serialized), event="history")

                # Check de cohérence sur les entités touchées ce tour. Best-effort :
                # tout est isolé dans un try/except interne pour qu'une panne du
                # judge n'empêche jamais l'événement `done`.
                try:
                    seen: set[str] = set()
                    for touched in deps.touched_ids:
                        verdict = await consistency_check(
                            driver, touched, deps.write_log, choice.profile
                        )
                        if not verdict.contradiction:
                            continue
                        # `message` = phrase courte pour l'auteur ; `reason` (le
                        # brouillon du judge) ne sert que de filet de secours.
                        alert_body = verdict.message.strip() or verdict.reason
                        # Dédup : une même contradiction remonte souvent depuis
                        # plusieurs entités touchées (voisinages qui se recouvrent)
                        # → une seule carte par tour.
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
                except Exception:
                    logger.exception("consistency_check a échoué (tour non bloqué)")

                yield ServerSentEvent(data="", event="done")
        except Exception as e:
            yield ServerSentEvent(data=str(e), event="error")

    return EventSourceResponse(event_generator())
