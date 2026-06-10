"""Tombstones des actions manuelles de l'auteur (:UserEdit) — human-in-the-loop (#61).

Quand l'auteur supprime/corrige une fiche DEPUIS L'UI, le LLM n'en sait rien :
l'entité vit encore dans l'historique threadé du maître et les extracteurs la
recréeraient au tour suivant. Chaque route d'édition pose donc un nœud léger
`:UserEdit {kind, name, detail, ts}` (hors du graphe :GenEntity — invisible des
tools), et la route de chat injecte EN CODE le bloc « décisions de l'auteur » :
- aux extracteurs, à CHAQUE tour tant que le tombstone vit (TTL) — c'est la
  garantie anti-résurrection ;
- au maître, UNE FOIS (flag `notified`) — le fil threadé garde la mémoire ensuite.

Même mécanique neuro-symbolique que le working set (cf. graph.render_recent_block) :
posé par du code, jamais par le modèle.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver


async def record_user_edit(driver: AsyncDriver, kind: str, name: str, detail: str) -> None:
    """Trace une action manuelle (kind: 'suppression' | 'correction').

    `detail` est la phrase injectée telle quelle au LLM — la rédiger côté route,
    complète et autoportante (« l'entité X (personnage) a été supprimée »)."""
    async with driver.session() as session:
        await session.run(
            "CREATE (:UserEdit {kind: $kind, name: $name, detail: $detail,"
            " ts: timestamp(), notified: false})",
            kind=kind, name=name, detail=detail,
        )


async def recent_user_edits(driver: AsyncDriver, limit: int, ttl_minutes: int) -> list[dict]:
    """Les actions manuelles encore vivantes (TTL), plus anciennes d'abord — et PURGE
    au passage celles qui ont expiré (un appel par tour de chat suffit comme GC).

    Le TTL borne la durée de la consigne « ne recrée pas » : passé ce délai,
    l'auteur peut réintroduire le même nom sans que le bloc s'y oppose."""
    cutoff_ms = ttl_minutes * 60_000
    async with driver.session() as session:
        await session.run(
            "MATCH (u:UserEdit) WHERE u.ts < timestamp() - $cutoff DELETE u",
            cutoff=cutoff_ms,
        )
        result = await session.run(
            """
            MATCH (u:UserEdit)
            RETURN u.kind AS kind, u.name AS name, u.detail AS detail
            ORDER BY u.ts DESC LIMIT $limit
            """,
            limit=limit,
        )
        rows = [dict(r) for r in await result.data()]
    rows.reverse()  # chronologique : la dernière action en dernier (la plus saillante)
    return rows


async def consume_unnotified_edits(driver: AsyncDriver) -> list[dict]:
    """Les actions pas encore annoncées au MAÎTRE — marquées `notified` au passage.

    Le maître est threadé : une fois le marqueur entré dans son fil, le répéter
    chaque tour ne ferait que gonfler l'historique. Read-and-mark atomique côté
    base ; si le tour échoue ensuite, les extracteurs (eux, stateless) reçoivent
    de toute façon le bloc complet à chaque tour."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (u:UserEdit) WHERE u.notified = false
            SET u.notified = true
            RETURN u.kind AS kind, u.name AS name, u.detail AS detail
            ORDER BY u.ts
            """
        )
        return [dict(r) for r in await result.data()]


def render_user_edits_block(rows: list[dict]) -> str:
    """Bloc « décisions de l'auteur » préfixé en code aux prompts (pur, testable).

    Rend "" sans action manuelle → le prompt reste nu, aucun cas dégénéré. Balisé
    comme contexte (pas du récit) et impératif : c'est l'AUTEUR qui a tranché,
    le modèle ne recrée pas ce qui a été supprimé et garde les valeurs corrigées."""
    if not rows:
        return ""
    listing = " ; ".join(r["detail"] for r in rows)
    return (
        "[CONTEXTE, pas du récit — l'auteur a corrigé la bible À LA MAIN depuis "
        f"l'interface : {listing}. Ces décisions sont définitives : ne recrée pas "
        "ce qui a été supprimé, garde les noms et valeurs corrigés.]"
    )
