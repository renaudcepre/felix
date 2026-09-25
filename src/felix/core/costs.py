"""Persistance du coût LLM par projet (#coût) — un nœud `:CostEntry` par
opération (tour de chat ou import de document), APPEND-ONLY : jamais un
compteur muté en place, l'agrégat se recalcule par somme (même esprit que
`:Message`, cf. `felix.core.messages`). `GET /api/costs?project=` (Étape
suivante, `felix.api.routes.costs`) lit `project_cost_totals` pour le total
persistant affiché dans la topbar du front.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from felix.cost import CostSummary


async def record_cost_entry(
    driver: AsyncDriver,
    summary: CostSummary,
    *,
    project: str,
    kind: str,
) -> None:
    """Enregistre le coût d'UNE opération sur le projet. `kind` = 'chat' | 'ingest'.

    `cost_usd` peut être `None` (au moins un modèle utilisé a un prix inconnu) —
    stocké tel quel, jamais remplacé par 0 (règle « jamais un faux 0 »,
    cf. felix.cost). No-op si l'opération n'a fait AUCUN appel LLM
    (total_tokens == 0) : pas de bruit dans le registre (ex. un tour de
    salutation sans extraction)."""
    if summary.total_tokens == 0:
        return
    async with driver.session() as session:
        await session.run(
            "MERGE (p:Project {id: $project})"
            " ON CREATE SET p.created_at = timestamp(), p.name = $project"
            " WITH p"
            " CREATE (e:CostEntry {"
            "   project: $project, kind: $kind,"
            "   request_tokens: $request_tokens, response_tokens: $response_tokens,"
            "   total_tokens: $total_tokens, cost_usd: $cost_usd,"
            "   at: timestamp()"
            " })"
            " CREATE (p)-[:HAS_COST]->(e)",
            project=project,
            kind=kind,
            request_tokens=summary.request_tokens,
            response_tokens=summary.response_tokens,
            total_tokens=summary.total_tokens,
            cost_usd=summary.cost_usd,
        )


async def project_cost_totals(driver: AsyncDriver, *, project: str) -> dict:
    """Totaux agrégés du projet : tokens in/out/total, USD total (None si AU
    MOINS une opération avait un prix inconnu — même règle que
    `CostLedger.summary`), et nombre d'opérations par nature (`kind`)."""
    async with driver.session() as session:
        result = await session.run(
            "MATCH (e:CostEntry {project: $project})"
            " RETURN e.kind AS kind, e.request_tokens AS request_tokens,"
            "  e.response_tokens AS response_tokens, e.total_tokens AS total_tokens,"
            "  e.cost_usd AS cost_usd",
            project=project,
        )
        rows = await result.data()

    request_tokens = sum(r["request_tokens"] for r in rows)
    response_tokens = sum(r["response_tokens"] for r in rows)
    total_tokens = sum(r["total_tokens"] for r in rows)
    count_by_kind: dict[str, int] = {}
    cost_usd: float | None = 0.0
    for r in rows:
        count_by_kind[r["kind"]] = count_by_kind.get(r["kind"], 0) + 1
        if r["cost_usd"] is None:
            cost_usd = None
        elif cost_usd is not None:
            cost_usd += r["cost_usd"]

    return {
        "request_tokens": request_tokens,
        "response_tokens": response_tokens,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
        "count_by_kind": count_by_kind,
    }
