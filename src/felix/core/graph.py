"""Accès graphe du noyau générique — modèle :GenEntity / :REL, Cypher pur.

Modèle de données volontairement minimal :
- nœuds ``:GenEntity`` {id (slug), name, entity_type, ...props libres (str)}
- relations ``:REL`` {rel_type, ...props libres} (type dynamique en propriété,
  Cypher pur sans APOC) ; une arête NARRATIVE (rel_type=NARRATIVE_REL) porte en
  plus {verbe (verbatim auteur), verbe_slug (clé de dédup)} — cf. #68

Aucune sémantique de domaine ici : ces helpers ne savent ni ce qu'est un
personnage ni ce qu'est une date — ils lisent et écrivent des entités libres.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from felix.ingest.resolver import slugify

if TYPE_CHECKING:
    from collections.abc import Iterable

    from neo4j import AsyncDriver

RESERVED_KEYS = {"id", "name", "entity_type"}

# Type GÉNÉRIQUE des relations narratives (#68) : le lien porte le verbe VERBATIM
# de l'auteur en propriété `verbe` (+ `verbe_slug`, sa forme normalisée qui sert
# de clé de MERGE — deux verbes différents entre la même paire = deux arêtes,
# la même paraphrase exacte n'en crée qu'une). Le type canonique reste réservé
# au noyau STRUCTUREL calculé en code (LOCATED_AT, PART_OF, MEMBER_OF,
# INVOLVES, NEXT).
NARRATIVE_REL = "LIE_A"

# Props d'arête posées par le code, jamais par `props` libre (cf. add_relation).
REL_RESERVED_KEYS = {"rel_type", "verbe", "verbe_slug"}


def rel_label(rel: dict) -> str:
    """Libellé d'une arête pour l'affichage/les prompts : le VERBE de l'auteur
    pour une arête narrative (« a —[était la maîtresse de]→ b »), le type
    canonique sinon. `rel` est une ligne d'all_relations (props inclus) ou
    directement un dict de propriétés d'arête."""
    props = rel.get("props", rel)
    if rel.get("rel_type", props.get("rel_type")) == NARRATIVE_REL:
        verbe = str(props.get("verbe", "")).strip()
        if verbe:
            return verbe
    return str(rel.get("rel_type", props.get("rel_type", "?")))


async def touch_entities(driver: AsyncDriver, ids: Iterable[str]) -> None:
    """Tamponne `last_touched` (ms epoch, horloge Neo4j) sur les entités données.

    Posé EN CODE par les tools à chaque écriture ET lecture résolue (jamais par le
    LLM) : c'est la matière du « working set » (cf. recent_entities) injecté aux
    extracteurs pour qu'ils VOIENT la base avant d'écrire."""
    id_list = [i for i in ids if i]
    if not id_list:
        return
    async with driver.session() as session:
        await session.run(
            "MATCH (e:GenEntity) WHERE e.id IN $ids SET e.last_touched = timestamp()",
            ids=id_list,
        )


async def recent_entities(driver: AsyncDriver, limit: int) -> list[dict]:
    """Les entités (non-événement) les plus récemment touchées, récentes d'abord.

    C'est la BORNE anti « toute la base dans le prompt » : à 400 entités, seules
    les N actives de l'histoire en cours remontent — les fiches d'un autre pan du
    monde, jamais touchées, restent derrière. `coalesce` car les nœuds d'avant le
    tampon n'ont pas `last_touched` (et Neo4j trie les null en PREMIER en DESC)."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (e:GenEntity) WHERE e.entity_type <> 'evenement'
            RETURN e.name AS name, e.entity_type AS entity_type
            ORDER BY coalesce(e.last_touched, 0) DESC, e.id
            LIMIT $limit
            """,
            limit=limit,
        )
        return [dict(r) for r in await result.data()]


def render_recent_block(rows: list[dict]) -> str:
    """Bloc « entités déjà en base » préfixé au prompt des extracteurs (pur, testable).

    L'ordre reçu est préservé (la récence EST l'information). Balisé comme contexte
    pour que l'extracteur ne le confonde pas avec du contenu d'auteur à extraire.
    Rend "" sur base vide → le prompt reste nu, aucun cas dégénéré."""
    if not rows:
        return ""
    listing = ", ".join(f"{r['name']} [{r['entity_type']}]" for r in rows)
    return (
        "[CONTEXTE, pas du récit — entités DÉJÀ en base (récentes d'abord) : "
        f"{listing}. Si le message donne un NOM à l'une d'elles ou dit que deux "
        "d'entre elles sont la même chose, utilise rename_entity ; pour un fait "
        "nouveau sur l'une d'elles, update_entity — ne crée JAMAIS de doublon.]"
    )


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


async def entity_events(driver: AsyncDriver, ref: str) -> list[dict]:
    """Événements ORDONNÉS impliquant une entité, en lignes brutes `{ordre, resume}`.

    Le sujet est résolu via `find_non_event` (un événement n'est jamais le sujet
    d'une chronologie, seulement un maillon). Rend `[]` si l'entité est introuvable
    ou n'a aucun événement. Source partagée de `entity_timeline` (texte pour le juge)
    et de la fiche d'entité de l'API (chronologie affichée)."""
    subject = await find_non_event(driver, ref)
    if not subject:
        return []
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (ev:GenEntity {entity_type: 'evenement'})
                  -[:REL {rel_type: 'INVOLVES'}]->(t:GenEntity {id: $id})
            RETURN ev.id AS id, ev.ordre AS ordre, ev.resume AS resume
            ORDER BY ev.ordre
            """,
            id=subject["id"],
        )
        return [dict(r) for r in await result.data()]


async def entity_timeline(driver: AsyncDriver, ref: str) -> str:
    """Chronologie ORDONNÉE des événements impliquant une entité (triés par `ordre`).

    Le checker a besoin de l'ORDRE pour distinguer « agit APRÈS sa mort »
    (contradiction) de « agit AVANT sa mort » (normal). `neighborhood` rend bien
    ces événements, mais NON triés et noyés parmi KNOWS/LOCATED_AT : le juge ne
    les ordonne pas de façon fiable. Ici on les isole et on les trie.

    Rend "" si l'entité est introuvable ou n'a aucun événement →
    auto-désactivation (pas de gate profil)."""
    rows = await entity_events(driver, ref)
    if not rows:
        return ""
    subject = await find_non_event(driver, ref)
    name = subject["name"] if subject else ref
    lines = [
        f"CHRONOLOGIE de {name} "
        "(événements où il/elle est impliqué(e), dans l'ordre) :"
    ]
    lines.extend(f"  #{r['ordre']} : {r['resume']}" for r in rows)
    return "\n".join(lines)


async def merge_entity_into(driver: AsyncDriver, src_id: str, dst_id: str) -> None:
    """Fusionne le nœud `src_id` DANS `dst_id` : relations ET événements rebranchés sur
    dst, propriétés manquantes recopiées (dst garde les siennes), puis src supprimé.
    Sans APOC — le modèle :REL { rel_type } se rebranche en Cypher pur. Les arêtes
    suivent le NŒUD (pas la valeur d'id), donc INVOLVES/NEXT des événements suivent."""
    async with driver.session() as session:
        # Relations SORTANTES de src → dst (éviter une boucle sur dst). Deux
        # passes : la clé de MERGE des arêtes NARRATIVES inclut le verbe_slug —
        # deux verbes différents vers le même voisin restent DEUX arêtes (sur la
        # clé rel_type seule, la 2e écraserait le verbe de la 1re, #68) ; les
        # structurelles gardent la clé rel_type (dédup contre une arête directe
        # préexistante de dst, qui n'a pas de verbe_slug).
        await session.run(
            "MATCH (f:GenEntity {id:$src})-[r:REL]->(o) "
            "WHERE o.id <> $dst AND r.rel_type <> $narr "
            "MATCH (t:GenEntity {id:$dst}) "
            "MERGE (t)-[nr:REL {rel_type: r.rel_type}]->(o) SET nr += properties(r)",
            src=src_id, dst=dst_id, narr=NARRATIVE_REL,
        )
        await session.run(
            "MATCH (f:GenEntity {id:$src})-[r:REL {rel_type: $narr}]->(o) "
            "WHERE o.id <> $dst "
            "MATCH (t:GenEntity {id:$dst}) "
            "MERGE (t)-[nr:REL {rel_type: $narr, "
            "verbe_slug: coalesce(r.verbe_slug, '')}]->(o) "
            "SET nr += properties(r)",
            src=src_id, dst=dst_id, narr=NARRATIVE_REL,
        )
        # Relations ENTRANTES vers src → dst (inclut les INVOLVES/LOCATED_AT
        # d'événements) — mêmes deux passes.
        await session.run(
            "MATCH (s)-[r:REL]->(f:GenEntity {id:$src}) "
            "WHERE s.id <> $dst AND r.rel_type <> $narr "
            "MATCH (t:GenEntity {id:$dst}) "
            "MERGE (s)-[nr:REL {rel_type: r.rel_type}]->(t) SET nr += properties(r)",
            src=src_id, dst=dst_id, narr=NARRATIVE_REL,
        )
        await session.run(
            "MATCH (s)-[r:REL {rel_type: $narr}]->(f:GenEntity {id:$src}) "
            "WHERE s.id <> $dst "
            "MATCH (t:GenEntity {id:$dst}) "
            "MERGE (s)-[nr:REL {rel_type: $narr, "
            "verbe_slug: coalesce(r.verbe_slug, '')}]->(t) "
            "SET nr += properties(r)",
            src=src_id, dst=dst_id, narr=NARRATIVE_REL,
        )
        # Props : dst garde les siennes, on complète avec celles que src a en plus.
        result = await session.run(
            "MATCH (f:GenEntity {id:$src}), (t:GenEntity {id:$dst}) "
            "RETURN properties(f) AS fp, properties(t) AS tp",
            src=src_id, dst=dst_id,
        )
        record = await result.single()
        if record:
            missing = {
                k: v for k, v in record["fp"].items()
                if k not in record["tp"] and k not in RESERVED_KEYS
            }
            if missing:
                await session.run(
                    "MATCH (t:GenEntity {id:$dst}) SET t += $props", dst=dst_id, props=missing,
                )
        await session.run("MATCH (f:GenEntity {id:$src}) DETACH DELETE f", src=src_id)


async def delete_entity(driver: AsyncDriver, entity_id: str) -> None:
    """Supprime une entité et toutes ses arêtes. Si c'est un ÉVÉNEMENT, la chaîne
    chronologique est RECOUSUE d'abord (p —NEXT→ e —NEXT→ n devient p —NEXT→ n) :
    sans ça, la timeline se casse en deux au premier maillon supprimé."""
    async with driver.session() as session:
        await session.run(
            """
            MATCH (p:GenEntity)-[:REL {rel_type: 'NEXT'}]->(e:GenEntity {id: $id})
                  -[:REL {rel_type: 'NEXT'}]->(n:GenEntity)
            MERGE (p)-[:REL {rel_type: 'NEXT'}]->(n)
            """,
            id=entity_id,
        )
        await session.run(
            "MATCH (e:GenEntity {id: $id}) DETACH DELETE e", id=entity_id,
        )


async def delete_relation(
    driver: AsyncDriver, from_id: str, to_id: str, rel_type: str,
    verbe_slug: str | None = None,
) -> bool:
    """Supprime UNE relation orientée (from —[rel_type]→ to). Rend False si elle
    n'existait pas (la clé vient du front — elle peut être périmée).

    `verbe_slug` complète la clé pour une arête NARRATIVE : plusieurs LIE_A
    peuvent lier la même paire (un par verbe) — sans lui, supprimer « aime »
    emporterait aussi « commande » (#68)."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:GenEntity {id: $a})-[r:REL {rel_type: $t}]->(b:GenEntity {id: $b})
            WHERE $vs IS NULL OR r.verbe_slug = $vs
            DELETE r RETURN count(r) AS n
            """,
            a=from_id, b=to_id, t=rel_type, vs=verbe_slug,
        )
        record = await result.single()
        return bool(record and record["n"])


@dataclass
class RenameOutcome:
    """Résultat d'un renommage driver-level — partagé par le tool `rename_entity`
    et la route PATCH de l'API (#61) : éditer un nom depuis l'UI DOIT avoir le
    même effet que le tool (id migré, relations/événements conservés, fusion sur
    collision). `final_id` n'a de sens que pour refreshed/merged/renamed."""

    status: str  # 'not_found' | 'invalid' | 'refreshed' | 'merged' | 'renamed'
    old_name: str = ""
    new_name: str = ""
    final_id: str = ""


async def rename_or_merge(driver: AsyncDriver, current_ref: str, new_name: str) -> RenameOutcome:
    """Renomme l'entité désignée par `current_ref` — ou la FUSIONNE si `new_name`
    désigne déjà une AUTRE entité (le nom canonique gagne)."""
    node = await find_node(driver, current_ref)
    if not node:
        return RenameOutcome("not_found")
    new_id = slugify(new_name)
    if not new_id:
        return RenameOutcome("invalid", old_name=node["name"])

    if new_id == node["id"]:  # même id (casse/espaces) : on rafraîchit juste le nom
        async with driver.session() as session:
            await session.run(
                "MATCH (e:GenEntity {id: $id}) SET e.name = $name",
                id=node["id"], name=new_name,
            )
        return RenameOutcome("refreshed", old_name=node["name"],
                             new_name=new_name, final_id=node["id"])

    target = await find_node(driver, new_id)
    if target and target["id"] != node["id"]:  # collision → FUSION dans le nom canonique
        await merge_entity_into(driver, node["id"], target["id"])
        return RenameOutcome("merged", old_name=node["name"],
                             new_name=target["name"], final_id=target["id"])

    # Renommage simple : migrer id + name. Les arêtes suivent le NŒUD, pas l'id.
    async with driver.session() as session:
        await session.run(
            "MATCH (e:GenEntity {id: $old}) SET e.id = $new, e.name = $name",
            old=node["id"], new=new_id, name=new_name,
        )
    return RenameOutcome("renamed", old_name=node["name"],
                         new_name=new_name, final_id=new_id)


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
        rel_props = {k: v for k, v in r["props"].items() if k not in REL_RESERVED_KEYS}
        rel_extra = f" ({fmt_props(rel_props, skip_reserved=False)})" if rel_props else ""
        # Arête narrative : le juge lit le VERBE exact de l'auteur (plus précis
        # qu'un type canonique), une structurelle garde son type (#68).
        lines.append(
            f"RELATION : {r['from']} —[{rel_label(r)}]→ {r['to']}{rel_extra}\n"
            f"  {other.get('name', other_id)} (type: {other.get('entity_type')})"
            f" · propriétés : {fmt_props(other)}"
        )
    return "\n".join(lines)
