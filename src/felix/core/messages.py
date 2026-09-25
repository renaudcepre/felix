"""Persistance de la conversation en graphe Neo4j — nœuds :Message (#63).

Deux lois structurelles gravées ici :

(a) TÉMOIGNAGE ≠ CANON. Les messages sont un journal d'interaction : ils
    attestent de ce qui a été dit, pas de ce qui est vrai. La bible
    (:GenEntity, avec les édits manuels de l'auteur) est le CANON. Tout conflit
    entre un message et la bible se résout EN FAVEUR DE LA BIBLE — c'est le but
    des tombstones :UserEdit (cf. user_edits.py). Ce module ne lit jamais la
    bible : il n'influence pas les prompts.

(b) PULL uniquement. Rien de ce module ne réinjecte automatiquement de vieux
    messages dans les prompts. « Vider la conversation » est une FONCTION ACTIVE
    (archive_conversation) : la page blanche est voulue, l'archive attend qu'on
    vienne la chercher (brique 3 du repêchage). Le seul état réinjecté
    automatiquement est le fil threadé du MAÎTRE (nœud :Thread), qui se charge
    à chaque tour si le front ne fournit pas d'historique — borne toujours par
    fenêtrage de tokens (window_history_by_tokens).

Nœud :Message (méta-nœud, hors :GenEntity, invisible des tools LLM) :
  id (UUID Cypher), project, role ('user'|'felix'), kind ('text'|'tool'|'alert'),
  body (texte), payload (JSON string ou null — toujours pour tool/alert ; pour
  text, null sauf pour la réponse felix qui clôt un tour, où il porte
  ``{"cost": CostSummary}`` — cf. felix.api.routes.atelier),
  ts (timestamp ms), ord (entier, continu par projet même après archivage),
  archived (bool, false à la création).

Relations posées à la création :
  (p:Project {id: project})-[:HAS_MESSAGE]->(m)   — ancre dans le registre
  (prev:Message {project, ord: max_ord})-[:NEXT]->(m) — chaîne chronologique

Nœud :Thread (un par projet, MERGE) :
  project, llm_history (JSON string pydantic-ai, null après archive)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver


async def record_message(  # noqa: PLR0913 — 6 params voulus : driver + 4 champs métier + project (keyword-only #60)
    driver: AsyncDriver,
    role: str,
    kind: str,
    body: str,
    payload: str | None = None,
    *,
    project: str,
) -> str:
    """Enregistre un message et retourne son UUID (généré par Cypher).

    Pose le nœud :Message avec l'ord suivant (MAX global du projet, archivés
    inclus — la numérotation ne repart jamais à zéro), chaîne en :NEXT depuis
    le message précédent, et rattache au :Project (MERGE auto-réparant : si le
    nœud n'existe pas encore, il est créé ; l'écart avec create_project est
    toléré en local-first).

    La question de l'auteur est persistée AVANT les passes LLM : si le tour
    crashe après, le message user reste en base — c'est voulu, il est le
    témoignage que la question a été posée."""
    async with driver.session() as session:
        result = await session.run(
            # Phase 1 : calcul du prochain ord (toutes tranches, archivées
            # comprises) et MERGE du projet dans le registre.
            "OPTIONAL MATCH (existing:Message {project: $project})"
            " WITH coalesce(max(existing.ord), 0) AS max_ord"
            " MERGE (p:Project {id: $project})"
            # Un projet né d'un message doit avoir un nom : sans lui, la liste
            # du registre (ProjectOut.name: str) plante tout le sélecteur.
            " ON CREATE SET p.created_at = timestamp(), p.name = $project"
            # Phase 2 : création du nœud Message et rattachement au projet.
            " CREATE (m:Message {"
            "   id: randomUUID(), project: $project,"
            "   role: $role, kind: $kind,"
            "   body: $body, payload: $payload,"
            "   ts: timestamp(), ord: max_ord + 1, archived: false"
            " })"
            " CREATE (p)-[:HAS_MESSAGE]->(m)"
            # Phase 3 : chaîne :NEXT depuis le message d'ord max (s'il existe).
            # FOREACH conditionnel : évite un OPTIONAL MATCH + subquery —
            # si prev est NULL (premier message du projet), rien ne se passe.
            " WITH m, max_ord"
            " OPTIONAL MATCH (prev:Message {project: $project, ord: max_ord})"
            " FOREACH (_ IN CASE WHEN prev IS NOT NULL THEN [1] ELSE [] END |"
            "   CREATE (prev)-[:NEXT]->(m)"
            " )"
            " RETURN m.id AS id",
            project=project,
            role=role,
            kind=kind,
            body=body,
            payload=payload,
        )
        record = await result.single()
        # La requête CREATE ne peut échouer silencieusement : si record est None,
        # la base a un problème structurel.
        if record is None:
            raise RuntimeError("record_message : nœud non créé — problème base")
        return str(record["id"])


async def link_produced(
    driver: AsyncDriver,
    message_id: str,
    entity_ids: set[str],
    *,
    project: str,
) -> None:
    """Pose les arêtes :PRODUCED depuis le message vers les entités touchées.

    Provenance : un message user → les entités écrites CE TOUR par les
    extracteurs. Permet de retrouver « quelles entités a créé ce message » pour
    le futur repêchage (brique 3).

    Scoping fort : MATCH (e:GenEntity {id: eid, project: $project}) —
    un id d'entité d'un AUTRE projet n'est pas trouvé, aucune arête n'est créée.
    Un id d'entité disparu (supprimé depuis) = pas d'arête, pas d'erreur
    (OPTIONAL MATCH, puis filtre WHERE e IS NOT NULL). No-op si entity_ids vide.
    """
    if not entity_ids:
        return
    async with driver.session() as session:
        await session.run(
            "MATCH (m:Message {id: $message_id, project: $project})"
            " WITH m"
            " UNWIND $entity_ids AS eid"
            " OPTIONAL MATCH (e:GenEntity {id: eid, project: $project})"
            " WITH m, e WHERE e IS NOT NULL"
            " MERGE (m)-[:PRODUCED]->(e)",
            message_id=message_id,
            project=project,
            entity_ids=list(entity_ids),
        )


async def conversation_messages(
    driver: AsyncDriver,
    *,
    project: str,
) -> list[dict]:
    """Messages NON archivés du projet, ordonnés par ord croissant.

    Rend les clés brutes : payload est la string JSON telle qu'en base (ou None
    pour kind='text'). La route API décode payload en dict avant de l'exposer
    (ConversationMessageOut). Les messages archivés sont invisibles ici : ils
    appartiennent à une conversation passée, accessibles uniquement via une
    requête explicite (repêchage, brique 3)."""
    async with driver.session() as session:
        result = await session.run(
            "MATCH (m:Message {project: $project, archived: false})"
            " RETURN m.id AS id, m.role AS role, m.kind AS kind,"
            "  m.body AS body, m.payload AS payload, m.ord AS ord"
            " ORDER BY m.ord",
            project=project,
        )
        return [dict(r) for r in await result.data()]


async def archive_conversation(
    driver: AsyncDriver,
    *,
    project: str,
) -> int:
    """Archive les messages actifs et remet le fil LLM à null.

    Archive ≠ suppression : les nœuds restent en base, la numérotation ord
    continue (le prochain record_message reprend à max_ord + 1 sur l'ensemble
    archivé + nouveau). « Nouvelle conversation » = page blanche SANS perte —
    les messages archivés sont la matière du futur repêchage (brique 3).

    Remet llm_history du :Thread à null : le fil threadé du maître est
    interrompu proprement (le front ne renvoie pas d'historique périmé, et
    load_llm_history retournera None jusqu'au prochain save)."""
    async with driver.session() as session:
        # Archivage atomique : tous les non-archivés du projet d'un coup.
        result = await session.run(
            "MATCH (m:Message {project: $project, archived: false})"
            " SET m.archived = true RETURN count(m) AS n",
            project=project,
        )
        record = await result.single()
        n: int = record["n"] if record else 0
        # Réinitialisation du fil threadé — no-op si :Thread n'existe pas encore.
        await session.run(
            "MATCH (t:Thread {project: $project}) SET t.llm_history = null",
            project=project,
        )
    return n


async def save_llm_history(
    driver: AsyncDriver,
    history_json: str,
    *,
    project: str,
) -> None:
    """Persiste le fil threadé du maître (blob JSON pydantic-ai) dans :Thread.

    Un seul nœud :Thread par projet (MERGE) : réentrant, idempotent. Le format
    est le résultat de ModelMessagesTypeAdapter.dump_python(mode='json') sérialisé —
    reconstruit à la lecture via validate_python(json.loads(raw))."""
    async with driver.session() as session:
        await session.run(
            "MERGE (t:Thread {project: $project}) SET t.llm_history = $history_json",
            project=project,
            history_json=history_json,
        )


async def load_llm_history(
    driver: AsyncDriver,
    *,
    project: str,
) -> str | None:
    """Charge le fil threadé du maître depuis :Thread, ou None si absent/réinitialisé.

    OPTIONAL MATCH : si aucun :Thread n'existe pour ce projet (première
    conversation, ou après archive_conversation), retourne None. La route
    traitera None comme « pas d'historique » et commencera un fil vierge.
    Après archive_conversation, llm_history est null → None aussi."""
    async with driver.session() as session:
        result = await session.run(
            "OPTIONAL MATCH (t:Thread {project: $project})"
            " RETURN t.llm_history AS llm_history",
            project=project,
        )
        record = await result.single()
        if record is None:
            return None
        value = record["llm_history"]
        return str(value) if value is not None else None
