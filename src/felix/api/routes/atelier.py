"""Route SSE du bot B (atelier) — texte streamé + cartes tool structurées.

Protocole d'événements (aligné sur le modèle AtelierMsg du front) :
- ``text``    : delta de texte du modèle
- ``tool``    : carte structurée émise par un tool (JSON ToolCard)
- ``usage``   : coût du tour — tokens + USD (JSON, cf. felix.cost.CostSummary)
- ``trace``   : appels d'outil + Cypher exécutée ce tour (#78, JSON, cf.
  felix.trace.TraceSummary)
- ``history`` : message_history sérialisé pour le tour suivant (JSON)
- ``alert``   : incohérence détectée par le check de cohérence (JSON, kind=alert)
- ``done`` / ``error``
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Query
from pydantic_ai.messages import ModelMessagesTypeAdapter
from sse_starlette import EventSourceResponse, ServerSentEvent

from felix.api.deps import (
    AtelierAgentsDep,
    ChronicleAgentsDep,
    GateAgentsDep,
    MasterAgentsDep,
    Neo4jDriver,
    RelationAgentsDep,
)
from felix.api.history import window_history_by_tokens
from felix.api.models import ChatRequest, ConversationMessageOut
from felix.atelier.agent import (
    ATELIER_CHOICES,
    DEFAULT_PROFILE,
    RouteDecision,
    build_turn_agents,
    profile_summary,
    resolve_profile,
)
from felix.atelier.pipeline import (
    consistency_alerts,
    run_extractors,
    sse_text,
    stream_pass,
)
from felix.config import settings
from felix.core import (
    GenericDeps,
    archive_conversation,
    consume_unnotified_alerts,
    consume_unnotified_edits,
    conversation_messages,
    link_produced,
    load_llm_history,
    recent_entities,
    recent_user_edits,
    record_cost_entry,
    record_message,
    render_alerts_block,
    render_recent_block,
    render_user_edits_block,
    save_llm_history,
)
from felix.core.projects import DEFAULT_PROJECT
from felix.cost import agent_model_name

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver
    from pydantic_ai import Agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/atelier", tags=["atelier"])


async def _master_prompt(driver: AsyncDriver, message: str, project: str) -> str:
    """Préfixe le message du maître de deux blocs « une fois » consommés :

    1. Décisions manuelles PAS ENCORE annoncées (#61) — tombstones :UserEdit.
    2. Alertes de cohérence PAS ENCORE annoncées (#50-a) — méta-nœuds :Alert.

    Les deux sont injectés UNE SEULE FOIS : le fil threadé du maître retient ensuite
    (répéter ne ferait que gonfler l'historique). Ordre : user_edits → alerts →
    message (les alertes portent sur le récit récent, après les décisions de bible).
    """
    edits_block = render_user_edits_block(
        await consume_unnotified_edits(driver, project=project)
    )
    alerts_block = render_alerts_block(
        await consume_unnotified_alerts(driver, project=project)
    )
    parts = [p for p in (edits_block, alerts_block, message) if p]
    return "\n\n".join(parts)


async def _apply_gate_verdict(
    gate_task: asyncio.Task[Any],
    gate_agent: Agent[None, RouteDecision],
    deps: GenericDeps,
) -> None:
    """Attend le gate et pose `extraction_requested`. Best-effort FAIL-CLOSED : si le
    gate crashe (transient LLM), on n'extrait pas ce tour — l'invariant produit n°1
    reste « jamais d'écriture sans contenu », et le fait peut être redonné.

    Le gate n'est pas joué via `stream_pass` (pas de cartes/texte à streamer) —
    son coût est donc déposé ICI dans `deps.cost_ledger`, seul appel qui échappe
    au dépôt automatique de `stream_pass`."""
    try:
        gate_run = await gate_task
        deps.cost_ledger.add_usage(agent_model_name(gate_agent), gate_run.usage())
        if gate_run.output.noter:
            deps.extraction_requested = True
            deps.write_log.append(
                f"contenu signalé pour extraction : {gate_run.output.fait.strip()}"
            )
    except Exception:
        logger.exception("gate de routage échoué (tour sans extraction)")


@router.get("/profiles")
async def atelier_profiles() -> list[dict[str, object]]:
    """Modes proposés par le sélecteur de l'UI (clé, libellé, vocabulaire UI,
    `evolving` — cf. `felix.atelier.agent.profile_summary`)."""
    return [profile_summary(c) for c in ATELIER_CHOICES.values()]


@router.post("/chat")
async def atelier_chat(  # noqa: PLR0913, PLR0915 — params FastAPI + setup avant le générateur
    body: ChatRequest,
    gate_agents: GateAgentsDep,
    master_agents: MasterAgentsDep,
    agents: AtelierAgentsDep,
    relation_agents: RelationAgentsDep,
    chronicle_agents: ChronicleAgentsDep,
    driver: Neo4jDriver,
) -> EventSourceResponse:
    choice = ATELIER_CHOICES.get(body.profile, ATELIER_CHOICES[DEFAULT_PROFILE])
    # Profil RÉEL de ce projet : pour un choix évolutif (#Étape 6), le profil
    # STOCKÉ (appris au fil des changements validés) s'il existe, sinon le seed —
    # UN SEUL appel par requête, réutilisé pour les 5 agents du tour (#82 : avant
    # ce fix, le maître et le gate restaient construits sur le seed pendant que
    # SEULS les 3 extracteurs étaient reconstruits pour ce profil). Un choix non
    # évolutif garde exactement le chemin d'aujourd'hui (dicts pré-construits).
    profile = await resolve_profile(driver, choice, project=body.project)
    if choice.evolving:
        turn = build_turn_agents(choice, profile)
        gate_agent, master_agent = turn.gate, turn.master
        agent, relation_agent, chronicle_agent = (
            turn.atelier,
            turn.relation,
            turn.chronicle,
        )
    else:
        gate_agent = gate_agents[choice.key]
        master_agent = master_agents[choice.key]
        agent = agents[choice.key]
        relation_agent = relation_agents[choice.key]
        chronicle_agent = chronicle_agents[choice.key]
    # Le projet/histoire courant vient du FRONT à chaque tour (stateless serveur).
    deps = GenericDeps(driver=driver, profile=profile, project_id=body.project)

    message_history = None
    if body.message_history:
        # Chemin eval/e2e : le front (ou le test) fournit un historique contrôlé —
        # prioritaire, on ne touche pas au :Thread. Borne toujours par budget.
        full = ModelMessagesTypeAdapter.validate_python(body.message_history)
        # Borne l'historique threadé par budget de tokens : on garde les tours
        # récents, le graphe (list_entities/find_entity) sert de mémoire longue.
        # Au niveau route plutôt que via history_processors → borne AUSSI le payload
        # SSE `history` renvoyé au front (réseau + mémoire front), pas que l'input modèle.
        message_history = window_history_by_tokens(full, settings.history_token_budget)
    else:
        # Chemin normal du front web (#63) : le fil est stocké côté serveur dans
        # :Thread, le front n'a plus besoin de gérer du localStorage. On charge,
        # on borne, et on garde le même chemin que ci-dessus.
        raw = await load_llm_history(driver, project=body.project)
        if raw is not None:
            full = ModelMessagesTypeAdapter.validate_python(json.loads(raw))
            message_history = window_history_by_tokens(
                full, settings.history_token_budget
            )

    async def event_generator() -> AsyncGenerator[ServerSentEvent]:
        # Persistance du message utilisateur dès l'entrée du tour (#63) : si une
        # passe LLM crashe ensuite, la question reste en base — c'est voulu (témoi-
        # gnage que la question a été posée, indépendamment du succès de la réponse).
        user_msg_id = await record_message(
            driver, "user", "text", body.message, project=body.project
        )
        # Buffer d'accumulation du texte streamé par le maître (deltas).
        master_text_buf: list[str] = []
        # Cartes collectées ce tour : (kind, data_json) pour tool et alert.
        turn_cards: list[tuple[str, str]] = []

        # GATE de routage STATELESS : décide si ce tour doit extraire, sur le message
        # SEUL (jamais le fil → l'ornière d'auto-imitation est impossible par
        # construction, issue #43). Lancé EN PARALLÈLE du maître : sa latence est
        # masquée par le stream de la réponse, on l'attend juste avant le dispatch.
        gate_task = asyncio.create_task(gate_agent.run(body.message))
        try:
            # Passe 0 « maître » : MÈNE la conversation (texte streamé), threadée.
            # La décision d'extraire ne lui appartient plus (cf. gate ci-dessus).
            yield ServerSentEvent(data="Felix répond…", event="phase")
            master: dict[str, Any] = {}
            async for ev in stream_pass(
                master_agent,
                await _master_prompt(driver, body.message, body.project),
                message_history,
                deps,
                stream_text=True,
                holder=master,
            ):
                yield ev
                # Accumulation du texte et collecte des cartes outil du maître.
                if ev.event == "text":
                    master_text_buf.append(sse_text(ev))
                elif ev.event == "tool":
                    turn_cards.append(("tool", sse_text(ev)))

            await _apply_gate_verdict(gate_task, gate_agent, deps)

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
                    await recent_entities(
                        driver, settings.recent_entities_limit, project=body.project
                    )
                )
                # Décisions manuelles de l'auteur (#61) : injectées à CHAQUE tour
                # d'extraction tant que le tombstone vit (TTL) — c'est la garantie
                # qu'une fiche supprimée depuis l'UI ne renaît pas via l'historique.
                edits_block = render_user_edits_block(
                    await recent_user_edits(
                        driver,
                        settings.user_edits_limit,
                        settings.user_edits_ttl_minutes,
                        project=body.project,
                    )
                )
                extract_prompt = "\n\n".join(
                    part for part in (edits_block, block, body.message) if part
                )
                # Boucle d'extraction PARTAGÉE (route ET ingestion) — cf.
                # felix.atelier.pipeline. Le chroniqueur (si le domaine en tient
                # un) reçoit le message NU, sans historique (sinon re-chronique).
                async for ev in run_extractors(
                    agent,
                    relation_agent,
                    chronicle_agent,
                    extract_prompt,
                    body.message,
                    message_history,
                    deps,
                    profile,
                ):
                    yield ev
                    if ev.event == "tool":
                        turn_cards.append(("tool", sse_text(ev)))

                # Check de cohérence (sur deps.check_candidates) — seulement si on a
                # extrait. Best-effort, isolé pour ne jamais bloquer le `done`.
                yield ServerSentEvent(data="Felix vérifie la cohérence…", event="phase")
                try:
                    async for alert in consistency_alerts(driver, deps, profile):
                        yield alert
                        turn_cards.append(("alert", sse_text(alert)))
                except Exception:
                    logger.exception("consistency_check a échoué (tour non bloqué)")

            # Coût du tour ENTIER (gate + maître + extracteurs + juge de cohérence) —
            # un seul système de comptabilité (deps.cost_ledger), alimenté par
            # chaque passe (cf. stream_pass / _apply_gate_verdict / consistency_check).
            cost_summary = deps.cost_ledger.summary()
            yield ServerSentEvent(data=cost_summary.model_dump_json(), event="usage")
            # Trace du tour ENTIER (#78) : appels d'outil + Cypher exécutée, mêmes
            # deps que le coût (cf. stream_pass, felix.trace.QueryTrace).
            trace_summary = deps.query_trace.summary()
            yield ServerSentEvent(data=trace_summary.model_dump_json(), event="trace")

            # L'historique threadé = le FIL DU MAÎTRE (la conversation), pas les
            # tool-calls d'extraction : le graphe est la mémoire longue, relue à la
            # demande. Plus léger, et la conversation reste cohérente d'un tour à l'autre.
            serialized = ModelMessagesTypeAdapter.dump_python(
                master["messages"], mode="json"
            )
            yield ServerSentEvent(data=json.dumps(serialized), event="history")

            # --- Persistance du tour en graphe (#63) ---
            # Ordre garanti : texte felix → cartes → provenance → fil threadé.
            # Exécuté APRÈS l'event history (compat e2e) et AVANT done.
            # Le coût ET la trace (#78) du tour sont attachés au DERNIER message
            # felix du tour (la dernière carte s'il y en a, sinon le texte) —
            # « sous chaque réponse » côté front veut dire une seule ligne par
            # tour, pas une par carte. Même paire que le coût : ça survit au
            # reload car persisté dans le MÊME payload.
            cost_json = cost_summary.model_dump()
            trace_json = trace_summary.model_dump()
            if master_text_buf:
                text_payload = (
                    None
                    if turn_cards
                    else json.dumps({"cost": cost_json, "trace": trace_json})
                )
                await record_message(
                    driver,
                    "felix",
                    "text",
                    "".join(master_text_buf),
                    payload=text_payload,
                    project=body.project,
                )
            for idx, (kind, card_data) in enumerate(turn_cards):
                card = json.loads(card_data)
                if idx == len(turn_cards) - 1:
                    card["cost"] = cost_json
                    card["trace"] = trace_json
                await record_message(
                    driver,
                    "felix",
                    kind,
                    "",
                    payload=json.dumps(card),
                    project=body.project,
                )
            # Coût persistant du projet (#coût) : accumulé en base pour le total
            # affiché dans la topbar, INDÉPENDAMMENT de l'historique des messages
            # (survit à « nouvelle conversation »/archivage).
            await record_cost_entry(
                driver, cost_summary, project=body.project, kind="chat"
            )
            # Provenance : le message de l'AUTEUR a produit les entités touchées
            # ce tour. Scoping fort : link_produced ne traverse pas les projets.
            await link_produced(
                driver, user_msg_id, deps.touched_ids, project=body.project
            )
            # Le fil threadé du maître est stocké côté serveur : le front web n'a
            # plus besoin de localStorage. Les evals/e2e qui fournissent
            # message_history continuent à fonctionner sans aucun changement.
            await save_llm_history(driver, json.dumps(serialized), project=body.project)

            yield ServerSentEvent(data="", event="done")
        except Exception as e:
            gate_task.cancel()
            yield ServerSentEvent(data=str(e), event="error")

    return EventSourceResponse(event_generator())


@router.get("/conversation")
async def get_conversation(
    driver: Neo4jDriver,
    project: str = Query(default=DEFAULT_PROJECT),
) -> list[ConversationMessageOut]:
    """Messages non archivés de la conversation active, ordonnés par ord.

    payload est décodé de JSON string (base) vers dict (API) — None pour la
    plupart des messages kind='text' (seule la réponse felix qui clôt un tour
    en porte un, ``{"cost": ...}``). Le front utilise cette route pour
    restaurer l'affichage après un rechargement de page (pas de localStorage)."""
    msgs = await conversation_messages(driver, project=project)
    out = []
    for m in msgs:
        payload_raw = m.get("payload")
        payload_dict: dict[str, Any] | None = None
        if payload_raw is not None:
            try:
                payload_dict = json.loads(payload_raw)
            except json.JSONDecodeError, TypeError:
                payload_dict = None
        out.append(
            ConversationMessageOut(
                id=m["id"],
                role=m["role"],
                kind=m["kind"],
                body=m.get("body") or "",
                ord=m["ord"],
                payload=payload_dict,
            )
        )
    return out


@router.post("/conversation/clear")
async def clear_conversation(
    driver: Neo4jDriver,
    project: str = Query(default=DEFAULT_PROJECT),
) -> dict[str, int]:
    """Archive la conversation active et remet le fil LLM à null.

    Archive ≠ suppression : les nœuds :Message restent en base pour le futur
    repêchage (brique 3). Après cet appel, conversation_messages retourne [],
    et load_llm_history retourne None — nouvelle conversation propre."""
    n = await archive_conversation(driver, project=project)
    return {"archived": n}
