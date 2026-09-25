"""Alertes de cohérence → maître : méta-nœud léger (:Alert) + consume-and-mark (#50-a).

Quand le vérificateur de cohérence émet une alerte en FIN de tour, le maître ne la
voit pas : il a déjà répondu. Même mécanique que les tombstones :UserEdit (#61) :
on pose un méta-nœud (:Alert) EN CODE, et la route injecte le bloc AU MAÎTRE au tour
SUIVANT, une seule fois (flag `notified`). Le fil threadé garde la mémoire ensuite.

Invisible des tools (hors :GenEntity), scopé par projet (#60).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver


async def record_alert(driver: AsyncDriver, body: str, *, project: str) -> None:
    """Pose un méta-nœud :Alert pour l'incohérence signalée ce tour.

    `body` = la phrase courte déjà rédigée par le vérificateur (le bloc s'y appuie
    telle quelle). Scopé par projet (#60) : une alerte de l'histoire A ne parasite
    jamais les prompts de l'histoire B.
    """
    async with driver.session() as session:
        await session.run(
            "CREATE (:Alert {body: $body, ts: timestamp(), notified: false,"
            " project: $project})",
            body=body,
            project=project,
        )


async def consume_unnotified_alerts(driver: AsyncDriver, *, project: str) -> list[str]:
    """Les alertes pas encore annoncées au MAÎTRE — marquées `notified` au passage.

    Read-and-mark atomique : le maître est threadé, une fois le bloc entré dans
    son fil, le répéter ne ferait que gonfler l'historique.
    Purge au passage les alertes notifiées de plus de 24 h (GC léger, comme la
    purge TTL de user_edits). Ordre chronologique (ts ASC) : l'alerte la plus
    ancienne en premier."""
    cutoff_ms = 24 * 60 * 60_000  # 24 h en millisecondes
    async with driver.session() as session:
        # GC léger : supprime les alertes déjà notifiées et expirées.
        await session.run(
            "MATCH (a:Alert {project: $project})"
            " WHERE a.notified = true AND a.ts < timestamp() - $cutoff DELETE a",
            project=project,
            cutoff=cutoff_ms,
        )
        # Read-and-mark atomique : renvoie ET marque en une seule transaction.
        result = await session.run(
            """
            MATCH (a:Alert {project: $project}) WHERE a.notified = false
            SET a.notified = true
            RETURN a.body AS body
            ORDER BY a.ts
            """,
            project=project,
        )
        return [r["body"] for r in await result.data()]


def render_alerts_block(bodies: list[str]) -> str:
    """Bloc d'alerte préfixé EN CODE au maître (pur, testable).

    Rend "" si aucune alerte → le prompt reste nu, aucun cas dégénéré. Balisé
    comme contexte (pas du récit), ton sobre conforme au MASTER_SYSTEM_PROMPT
    (bloc-notes, pas interviewer) : signaler en une phrase sans questionner.
    """
    if not bodies:
        return ""
    listing = " ; ".join(f"« {b} »" for b in bodies)
    return (
        "[CONTEXTE, pas du récit — le vérificateur de cohérence a relevé ceci APRÈS "
        f"ta dernière réplique : {listing}. Si c'est toujours pertinent, SIGNALE-LE "
        "à l'auteur en une phrase sobre au début de ta réplique (incohérence possible, "
        "piste flash-back ou erreur chronologique) — sans questionner. Si le message "
        "de l'auteur corrige déjà cela, n'en parle pas.]"
    )
