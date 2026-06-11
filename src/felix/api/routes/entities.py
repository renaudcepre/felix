"""Routes schemaless — modèle :GenEntity / :REL du copilote (bot B).

Lecture : listes filtrables par `entity_type` et fiche générique (props libres +
relations + chronologie), sans aucune sémantique de domaine ni structure garantie.

Écriture (#61, human-in-the-loop) : l'auteur corrige/supprime DEPUIS L'UI ce que
le LLM a mal modélisé. Chaque action manuelle pose un tombstone `:UserEdit`
(felix.core.user_edits) que la route de chat injecte au LLM — sinon l'entité
supprimée renaît au tour suivant via l'historique threadé.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from felix.api.deps import Neo4jDriver
from felix.api.models import (
    EntityDetail,
    EntityEventOut,
    EntityPatch,
    EntityRef,
    EntityRelationOut,
    EntitySummary,
)
from felix.core.graph import (
    RESERVED_KEYS,
    all_entities,
    all_relations,
    delete_entity,
    delete_relation,
    entity_events,
    find_node,
    rename_or_merge,
    touch_entities,
)
from felix.core.user_edits import record_user_edit

router = APIRouter(prefix="/api/entities", tags=["entities"])

# Machinerie d'événements : ces relations ne sont pas des liens « fiche à fiche »
# (INVOLVES = participation à un event, NEXT = chaîne chronologique). La
# chronologie de l'entité les restitue déjà, ordonnées, dans `events`.
_EVENT_RELS = {"INVOLVES", "NEXT", "LOCATED_AT"}


def _props(entity: dict) -> dict:
    return {k: v for k, v in entity.items() if k not in RESERVED_KEYS}


@router.get("")
async def list_entities(
    driver: Neo4jDriver,
    type: str | None = Query(default=None),  # paramètre d'URL public (type d'entité)
) -> list[EntitySummary]:
    """Entités filtrées par `entity_type`. Sans filtre : tout sauf les événements
    (la chronologie n'est pas une liste de fiches)."""
    entities = await all_entities(driver)
    summaries = []
    for e in entities:
        etype = e.get("entity_type")
        if type is None:
            if etype == "evenement":
                continue
        elif etype != type:
            continue
        summaries.append(
            EntitySummary(
                id=e["id"],
                name=e.get("name", e["id"]),
                entity_type=etype,
                props=_props(e),
            )
        )
    return summaries


@router.get("/{entity_id}")
async def get_entity(entity_id: str, driver: Neo4jDriver) -> EntityDetail:
    node = await find_node(driver, entity_id)
    if not node:
        raise HTTPException(status_code=404, detail="Entity not found")

    node_id = node["id"]
    index = {e["id"]: e for e in await all_entities(driver)}

    relations: list[EntityRelationOut] = []
    for r in await all_relations(driver):
        if r["rel_type"] in _EVENT_RELS:
            continue
        if node_id == r["from"]:
            other_id, direction = r["to"], "out"
        elif node_id == r["to"]:
            other_id, direction = r["from"], "in"
        else:
            continue
        other = index.get(other_id, {"id": other_id, "name": other_id})
        props = r.get("props", {})
        relations.append(
            EntityRelationOut(
                rel_type=r["rel_type"],
                direction=direction,
                other=EntityRef(
                    id=other["id"],
                    name=other.get("name", other["id"]),
                    entity_type=other.get("entity_type"),
                ),
                verbe=props.get("verbe"),
                verbe_slug=props.get("verbe_slug"),
            )
        )

    events = [
        EntityEventOut(id=row["id"], ordre=row["ordre"], resume=row["resume"])
        for row in await entity_events(driver, node_id)
    ]

    return EntityDetail(
        id=node_id,
        name=node.get("name", node_id),
        entity_type=node.get("entity_type"),
        props=_props(node),
        relations=relations,
        events=events,
    )


# --- Édition manuelle (#61) — chaque action laisse un tombstone :UserEdit ---


def _label(node: dict) -> str:
    """Libellé autoportant pour le tombstone : un événement se désigne par son
    résumé (son « nom » EST l'action), une fiche par nom (type)."""
    if node.get("entity_type") == "evenement":
        return f"l'événement « {node.get('resume', node.get('name', node['id']))} »"
    return f"l'entité « {node.get('name', node['id'])} » ({node.get('entity_type', '?')})"


@router.delete("/{entity_id}")
async def remove_entity(entity_id: str, driver: Neo4jDriver) -> dict:
    node = await find_node(driver, entity_id)
    if not node:
        raise HTTPException(status_code=404, detail="Entity not found")
    label = _label(node)
    await delete_entity(driver, node["id"])
    await record_user_edit(
        driver, "suppression", node.get("name", node["id"]),
        f"{label} a été supprimé(e)",
    )
    return {"deleted": node["id"]}


@router.patch("/{entity_id}")
async def patch_entity(entity_id: str, patch: EntityPatch, driver: Neo4jDriver) -> dict:
    """Correction manuelle d'une fiche : rename (MÊME effet que le tool
    rename_entity — id migré, fusion sur collision, relations/événements
    conservés), pose/retrait de propriétés. Chaque action = un tombstone."""
    node = await find_node(driver, entity_id)
    if not node:
        raise HTTPException(status_code=404, detail="Entity not found")
    final_id, merged = node["id"], False

    if patch.name and patch.name.strip() and patch.name != node.get("name"):
        out = await rename_or_merge(driver, node["id"], patch.name)
        if out.status == "invalid":
            raise HTTPException(status_code=422, detail=f"Nom invalide : {patch.name!r}")
        final_id, merged = out.final_id, out.status == "merged"
        detail = (
            f"« {out.old_name} » et « {out.new_name} » étaient la même entité — fusionnées"
            if merged else f"« {out.old_name} » a été renommé(e) « {out.new_name} »"
        )
        await record_user_edit(driver, "correction", out.new_name, detail)

    to_set = {k: v for k, v in patch.props.items() if k not in RESERVED_KEYS}
    if to_set:
        async with driver.session() as session:
            await session.run(
                "MATCH (e:GenEntity {id: $id}) SET e += $props",
                id=final_id, props=to_set,
            )
        name = patch.name or node.get("name", final_id)
        for key, value in to_set.items():
            old = node.get(key)
            detail = (
                f"la propriété {key} de « {name} » a été corrigée : "
                f"{old!r} → {value!r}" if old is not None
                else f"la propriété {key} de « {name} » a été fixée à {value!r}"
            )
            await record_user_edit(driver, "correction", name, detail)

    to_remove = [k for k in patch.remove_props if k not in RESERVED_KEYS]
    if to_remove:
        async with driver.session() as session:
            for key in to_remove:
                await session.run(
                    f"MATCH (e:GenEntity {{id: $id}}) REMOVE e.`{key.replace('`', '')}`",
                    id=final_id,
                )
        name = patch.name or node.get("name", final_id)
        for key in to_remove:
            await record_user_edit(
                driver, "suppression", name,
                f"la propriété {key} de « {name} » a été supprimée",
            )

    # La fiche corrigée entre dans le working set : les extracteurs la VOIENT.
    await touch_entities(driver, [final_id])
    return {"id": final_id, "merged": merged}


@router.delete("/{entity_id}/relations/{rel_type}/{other_id}")
async def remove_relation(
    entity_id: str, rel_type: str, other_id: str, driver: Neo4jDriver,
    verbe_slug: str | None = Query(default=None),
) -> dict:
    """Supprime la relation ORIENTÉE entity —[rel_type]→ other (la direction
    affichée sur la fiche/carte est celle de la clé). Pour une arête narrative
    (LIE_A), `verbe_slug` complète la clé : la même paire peut porter plusieurs
    arêtes, une par verbe — sans lui on les supprimerait toutes (#68)."""
    a = await find_node(driver, entity_id)
    b = await find_node(driver, other_id)
    if not a or not b:
        raise HTTPException(status_code=404, detail="Entity not found")
    if not await delete_relation(driver, a["id"], b["id"], rel_type, verbe_slug):
        raise HTTPException(status_code=404, detail="Relation not found")
    label = rel_type if verbe_slug is None else f"{rel_type} « {verbe_slug} »"
    await record_user_edit(
        driver, "suppression", a.get("name", a["id"]),
        f"la relation {a.get('name', a['id'])} —[{label}]→ "
        f"{b.get('name', b['id'])} a été supprimée (elle était fausse)",
    )
    return {"deleted": f"{a['id']} -[{label}]-> {b['id']}"}
