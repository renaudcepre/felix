"""Pipeline d'extraction PARTAGÉ — une seule implémentation, deux appelants.

Le tour de chat (route SSE `/api/atelier/chat`) et l'ingestion de document
(`felix.ingest.document.ingest_document`, Étape 2) jouent tous les deux la même
boucle entités → relieur → chroniqueur-si-`runs_chronicle(profile)`, avec le
même comportement best-effort (une passe qui échoue est journalisée et
n'interrompt pas les suivantes). « Des systèmes, pas des copies » : ce module
est CE code, écrit une fois, utilisé par les deux.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from sse_starlette import ServerSentEvent

from felix.core import consistency_check, record_alert, runs_chronicle, source_pages_for
from felix.core.check import (
    CheckVerdict,
    distinct_contradictions,
    verify_against_source,
)
from felix.core.graph import find_node
from felix.cost import agent_model_name

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

    from felix.core import GenericDeps, Profile

logger = logging.getLogger(__name__)


def sse_text(ev: ServerSentEvent) -> str:
    """`ServerSentEvent.data` est typé `Any | None` côté sse_starlette (la lib
    ne le contraint pas) ; toutes les passes de ce module (et les deux routes
    qui les consomment, atelier ET ingestion) n'y déposent jamais que du texte
    — ce garde-fou le dit au vérificateur de types, sans changer le comportement."""
    assert isinstance(ev.data, str)
    return ev.data


async def stream_pass(  # noqa: PLR0913 — une passe = agent + prompt + historique + deps partagés
    sub_agent: Agent[GenericDeps, str], prompt: str, history: list | None, deps: GenericDeps,
    *, stream_text: bool, holder: dict
) -> AsyncGenerator[ServerSentEvent]:
    """Joue une passe via `.iter()` : draine les cartes des tools EN LIVE (à
    chaque node) et, si `stream_text`, streame le texte. Stocke `usage` +
    `messages` dans `holder` (un générateur ne peut pas « return »). Factorisé
    pour toutes les passes : maître (texte streamé) ; extracteurs (cartes live, pas
    de texte → une seule bulle). `prompt` varie : message nu pour le maître et
    le chroniqueur, message préfixé du working set pour entités/relieur.

    Dépose AUSSI le coût de cette passe dans `deps.cost_ledger` — attribué au
    modèle RÉELLEMENT utilisé par `sub_agent` (gate/maître/extracteurs peuvent
    différer, cf. build_gate_model/build_checker_model/build_chat_model) : un
    seul système de comptabilité, alimenté par chaque passe."""
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
        usage = run.usage()
        holder["usage"] = usage
        holder["messages"] = run.all_messages()
        deps.cost_ledger.add_usage(agent_model_name(sub_agent), usage)


async def run_extractors(  # noqa: PLR0913 — 3 agents + 2 prompts + deps/profile, un seul appelant par tour
    agent: Agent[GenericDeps, str],
    relation_agent: Agent[GenericDeps, str],
    chronicle_agent: Agent[GenericDeps, str],
    extract_prompt: str,
    chronicle_prompt: str,
    message_history: list | None,
    deps: GenericDeps,
    profile: Profile | None,
) -> AsyncGenerator[ServerSentEvent]:
    """Boucle d'extraction PARTAGÉE : entités → relieur → chroniqueur (si le
    domaine tient une chronologie). Chaque passe est BEST-EFFORT — une passe
    qui échoue est journalisée (log + continue), le tour (ou le bloc en cours
    d'ingestion) n'est jamais bloqué.

    `extract_prompt` porte le working set + les décisions de l'auteur + le
    contenu à extraire (entités/relieur) ; `chronicle_prompt` est le contenu
    NU (le chroniqueur ne reçoit ni working set ni historique — il ne crée pas
    d'entité, seulement des événements). Le coût de chaque passe réussie est
    déposé dans `deps.cost_ledger` par `stream_pass` lui-même (pas de liste
    `usages` séparée à tenir ici).
    """
    passes = [
        (agent, "entités", extract_prompt, message_history,
         "Felix met à jour la bible…"),
        (relation_agent, "relations", extract_prompt, message_history,
         "Felix relie les fiches…"),
    ]
    # Chroniqueur sauté pour un domaine sans chronologie (#Étape 1.3) : une fiche
    # maintenance décrit un état stable, pas un déroulé — règle SYSTÉMIQUE unique
    # (runs_chronicle), partagée par la route et l'ingestion.
    if runs_chronicle(profile):
        passes.append((
            chronicle_agent, "événements", chronicle_prompt, None,
            "Felix note les événements…",
        ))
    for sub_agent, label, prompt, hist, phase_text in passes:
        try:
            yield ServerSentEvent(data=phase_text, event="phase")
            sub: dict = {}
            async for ev in stream_pass(
                sub_agent, prompt, hist, deps, stream_text=False, holder=sub
            ):
                yield ev
        except Exception:
            logger.exception("passe %s échouée (tour non bloqué)", label)


# Titre affiché selon le verdict du vérificateur source (cf. verify_against_source) —
# « document » = vraie anomalie métier, « extraction »/« unverifiable » restent
# une incohérence POSSIBLE (source non prouvée fautive, ou pas de source du tout).
_ALERT_TITLES = {
    "document": "Incohérence dans le document",
    "extraction": "Felix a peut-être mal lu le document",
}
_DEFAULT_ALERT_TITLE = "Incohérence possible"


async def _source_pages_for_subjects(
    driver: AsyncDriver, sujets: list[str], *, project: str
) -> list[tuple[str, int, str]]:
    """Résout les NOMS de sujets d'un verdict (cf. CheckVerdict.sujets) vers
    leurs pages sources. Un sujet non résolu (nom légèrement reformulé par le
    judge) n'apporte simplement aucune page — `verify_against_source` retombe
    alors sur `unverifiable`, sans cas particulier à gérer ici."""
    ids = []
    for name in sujets:
        node = await find_node(driver, name, project=project)
        if node:
            ids.append(node["id"])
    return await source_pages_for(driver, ids, project=project)


async def consistency_alerts(
    driver: AsyncDriver, deps: GenericDeps, profile: Profile | None
) -> AsyncGenerator[ServerSentEvent]:
    """Carte `alert` par contradiction DISTINCTE sur les entités touchées ce tour.

    Dédupliqué : une même incohérence remonte souvent de plusieurs entités voisines
    (voisinages qui se recouvrent) → une seule carte par tour. `message` = phrase
    courte pour l'auteur ; `reason` (brouillon du judge) sert de filet de secours.

    Chaque contradiction DISTINCTE est ensuite passée à `verify_against_source`
    (UN appel LLM par alerte, jamais par entité — cf. la boucle ci-dessous, après
    `distinct_contradictions`) pour distinguer une vraie incohérence du DOCUMENT
    d'une mauvaise LECTURE de Felix à l'extraction : la carte porte alors
    `source_kind` (document/extraction/unverifiable) et une `correction` si le
    vérificateur peut l'énoncer.
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
        *(consistency_check(driver, i, deps.write_log, profile,
                            project=deps.project_id, cost_ledger=deps.cost_ledger)
          for i in ids),
        return_exceptions=True,
    )
    ok: list[CheckVerdict] = []
    for verdict in verdicts:
        if isinstance(verdict, BaseException):
            logger.warning("un check a échoué (ignoré) : %r", verdict)
            continue
        ok.append(verdict)
    for verdict in distinct_contradictions(ok):
        alert_body = verdict.message.strip() or verdict.reason
        # UN appel LLM par alerte DISTINCTE (jamais par entité) — coût compté
        # dans deps.cost_ledger comme toute autre passe (cf. CLAUDE.md « des
        # systèmes, pas du cas par cas »).
        pages = await _source_pages_for_subjects(
            driver, verdict.sujets, project=deps.project_id
        )
        source_verdict = await verify_against_source(verdict, pages, deps.cost_ledger)
        title = _ALERT_TITLES.get(source_verdict.kind, _DEFAULT_ALERT_TITLE)
        yield ServerSentEvent(
            data=json.dumps({
                "kind": "alert",
                "title": title,
                "body": alert_body,
                "status": "open",
                "source_kind": source_verdict.kind,
                "correction": source_verdict.correction,
            }),
            event="alert",
        )
        # Persist pour le tour suivant (#50-a) : le maître recevra ce bloc
        # au prochain appel via consume_unnotified_alerts dans _master_prompt.
        await record_alert(driver, alert_body, project=deps.project_id)
