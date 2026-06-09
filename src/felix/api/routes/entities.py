"""Routes de lecture schemaless — modèle :GenEntity / :REL du copilote (bot B).

Expose ce que le copilote a modélisé, sans aucune sémantique de domaine :
listes filtrables par `entity_type` et fiche générique (props libres + relations
+ chronologie). Robuste à une structure non garantie : on ne suppose jamais
qu'une entité possède tel ou tel champ.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from felix.api.deps import Neo4jDriver
from felix.api.models import (
    EntityDetail,
    EntityEventOut,
    EntityRef,
    EntityRelationOut,
    EntitySummary,
)
from felix.core.graph import (
    RESERVED_KEYS,
    all_entities,
    all_relations,
    entity_events,
    find_node,
)

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
    type: str | None = Query(default=None),  # noqa: A002 — paramètre d'URL public
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
        relations.append(
            EntityRelationOut(
                rel_type=r["rel_type"],
                direction=direction,
                other=EntityRef(
                    id=other["id"],
                    name=other.get("name", other["id"]),
                    entity_type=other.get("entity_type"),
                ),
            )
        )

    events = [
        EntityEventOut(ordre=row["ordre"], resume=row["resume"])
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
