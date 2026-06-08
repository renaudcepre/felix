"""Accès graphe du noyau générique — modèle :GenEntity / :REL, Cypher pur.

Modèle de données volontairement minimal :
- nœuds ``:GenEntity`` {id (slug), name, entity_type, ...props libres (str)}
- relations ``:REL`` {rel_type, ...props libres} (type dynamique en propriété,
  Cypher pur sans APOC)

Aucune sémantique de domaine ici : ces helpers ne savent ni ce qu'est un
personnage ni ce qu'est une date — ils lisent et écrivent des entités libres.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from felix.ingest.resolver import slugify

if TYPE_CHECKING:
    from neo4j import AsyncDriver

RESERVED_KEYS = {"id", "name", "entity_type"}


async def find_node(driver: AsyncDriver, ref: str) -> dict | None:
    """Entité par slug exact, sinon par nom (contains, insensible à la casse).

    Tie-break : on PRÉFÈRE l'id qui matche exactement, puis une entité
    NON-événement. Sans tri, find_node("borin") pourrait rendre l'événement
    « le Baron abat Borin » (name CONTAINS) au lieu du personnage → mauvais
    sous-graphe au check. Préférer l'id-exact + le non-événement est le
    comportement voulu partout (find_entity, dup-check, neighborhood…)."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (e:GenEntity)
            WHERE e.id = $slug OR toLower(e.name) CONTAINS toLower($ref)
            RETURN e
            ORDER BY CASE WHEN e.id = $slug THEN 0 ELSE 1 END,
                     CASE WHEN e.entity_type = 'evenement' THEN 1 ELSE 0 END
            LIMIT 1
            """,
            slug=slugify(ref),
            ref=ref,
        )
        record = await result.single()
        return dict(record["e"]) if record else None


async def find_non_event(driver: AsyncDriver, ref: str) -> dict | None:
    """Comme find_node mais IGNORE les nodes événement (entity_type='evenement').

    Les participants d'un événement et les extrémités d'une relation entre entités
    sont de VRAIES entités (personnage/lieu/objet…), jamais des événements — sinon
    on relie des actions comme si c'étaient des choses (« Vance FIGHTS [event] »,
    ou un événement qui se résout vers lui-même par collision de nom).
    """
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (e:GenEntity)
            WHERE e.entity_type <> 'evenement'
              AND (e.id = $slug OR toLower(e.name) CONTAINS toLower($ref))
            RETURN e LIMIT 1
            """,
            slug=slugify(ref),
            ref=ref,
        )
        record = await result.single()
        return dict(record["e"]) if record else None


async def entity_timeline(driver: AsyncDriver, ref: str) -> str:
    """Chronologie ORDONNÉE des événements impliquant une entité (triés par `ordre`).

    Le checker a besoin de l'ORDRE pour distinguer « agit APRÈS sa mort »
    (contradiction) de « agit AVANT sa mort » (normal). `neighborhood` rend bien
    ces événements, mais NON triés et noyés parmi KNOWS/LOCATED_AT : le juge ne
    les ordonne pas de façon fiable. Ici on les isole et on les trie.

    Le sujet est résolu via `find_non_event` (un événement n'est jamais le sujet
    d'une chronologie, seulement un maillon). Rend "" si l'entité est introuvable
    ou n'a aucun événement → auto-désactivation (pas de gate profil)."""
    subject = await find_non_event(driver, ref)
    if not subject:
        return ""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (ev:GenEntity {entity_type: 'evenement'})
                  -[:REL {rel_type: 'INVOLVES'}]->(t:GenEntity {id: $id})
            RETURN ev.ordre AS ordre, ev.resume AS resume
            ORDER BY ev.ordre
            """,
            id=subject["id"],
        )
        rows = await result.data()
    if not rows:
        return ""
    lines = [
        f"CHRONOLOGIE de {subject['name']} "
        "(événements où il/elle est impliqué(e), dans l'ordre) :"
    ]
    lines.extend(f"  #{r['ordre']} : {r['resume']}" for r in rows)
    return "\n".join(lines)


async def all_entities(driver: AsyncDriver) -> list[dict]:
    async with driver.session() as session:
        result = await session.run("MATCH (e:GenEntity) RETURN e ORDER BY e.id")
        return [dict(r["e"]) for r in await result.data()]


async def all_relations(driver: AsyncDriver) -> list[dict]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:GenEntity)-[r:REL]->(b:GenEntity)
            RETURN a.id AS from, r.rel_type AS rel_type, properties(r) AS props, b.id AS to
            """
        )
        return [dict(r) for r in await result.data()]


def fmt_props(props: dict, *, skip_reserved: bool = True) -> str:
    items = [
        f"{k}={v!r}" for k, v in sorted(props.items())
        if not (skip_reserved and k in RESERVED_KEYS)
    ]
    return ", ".join(items) if items else "(aucune propriété)"


async def neighborhood(driver: AsyncDriver, ref: str) -> str | None:
    """Sous-graphe 1-hop de l'entité : props complètes + relations + voisins complets."""
    node = await find_node(driver, ref)
    if not node:
        return None
    relations = await all_relations(driver)
    entities = {e["id"]: e for e in await all_entities(driver)}

    lines = [f"ENTITÉ : {node['name']} (type: {node.get('entity_type')})",
             f"  propriétés : {fmt_props(node)}"]
    for r in relations:
        if node["id"] not in (r["from"], r["to"]):
            continue
        other_id = r["to"] if r["from"] == node["id"] else r["from"]
        other = entities.get(other_id, {})
        rel_props = {k: v for k, v in r["props"].items() if k != "rel_type"}
        rel_extra = f" ({fmt_props(rel_props, skip_reserved=False)})" if rel_props else ""
        lines.append(
            f"RELATION : {r['from']} —[{r['rel_type']}]→ {r['to']}{rel_extra}\n"
            f"  {other.get('name', other_id)} (type: {other.get('entity_type')})"
            f" · propriétés : {fmt_props(other)}"
        )
    return "\n".join(lines)
