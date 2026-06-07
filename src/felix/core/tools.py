"""Les 5 tools du noyau générique — lecture/écriture d'entités libres :GenEntity.

Les docstrings portent la DISCIPLINE de schéma émergent (réutiliser types et noms
de propriétés existants plutôt que d'en inventer) : c'est par elles que le petit
modèle tient le cap, pas par du code. Ne pas les diluer.
"""
from __future__ import annotations

from pydantic_ai import RunContext

from felix.core.deps import GenericDeps
from felix.core.graph import (
    RESERVED_KEYS,
    all_entities,
    all_relations,
    find_node,
    fmt_props,
)
from felix.core.models import ToolCard
from felix.ingest.resolver import slugify


async def describe_schema(ctx: RunContext[GenericDeps]) -> str:
    """Décrit le schéma actuel de la base : types d'entités, noms de propriétés
    et types de relations déjà utilisés.

    À appeler AVANT toute écriture, pour réutiliser les types et noms de
    propriétés existants au lieu d'en inventer de nouveaux.
    """
    entities = await all_entities(ctx.deps.driver)
    relations = await all_relations(ctx.deps.driver)
    if not entities:
        if ctx.deps.profile is not None:
            return ctx.deps.profile.render_schema_hint()
        return "Base vide : aucun type, aucune propriété. Tu définis le schéma."

    by_type: dict[str, dict] = {}
    for e in entities:
        t = e.get("entity_type", "?")
        slot = by_type.setdefault(t, {"count": 0, "keys": set()})
        slot["count"] += 1
        slot["keys"].update(k for k in e if k not in RESERVED_KEYS)

    lines = ["Types d'entités existants :"]
    for t, slot in sorted(by_type.items()):
        keys = ", ".join(sorted(slot["keys"])) or "—"
        lines.append(f"- {t} ({slot['count']}) · propriétés : {keys}")

    rel_types = sorted({r["rel_type"] for r in relations})
    lines.append(f"Types de relations : {', '.join(rel_types) if rel_types else '—'}")
    return "\n".join(lines)


async def list_entities(ctx: RunContext[GenericDeps]) -> str:
    """Liste toutes les entités de la base (nom + type), groupées par type.

    À appeler pour répondre à une question sur le CONTENU de la base (« qu'y
    a-t-il ? », « qui sont les personnages ? ») ou pour voir ce qui existe déjà
    avant de créer. Ne devine jamais le contenu : lis-le ici.
    """
    entities = await all_entities(ctx.deps.driver)
    if not entities:
        return "La base est vide."
    by_type: dict[str, list[str]] = {}
    for e in entities:
        by_type.setdefault(e.get("entity_type", "?"), []).append(
            e.get("name", e.get("id", "?"))
        )
    return "\n".join(
        f"{t} ({len(names)}) : {', '.join(names)}" for t, names in sorted(by_type.items())
    )


async def find_entity(ctx: RunContext[GenericDeps], name: str) -> str:
    """Cherche une entité par nom et retourne ses propriétés et relations.

    Args:
        name: Nom complet ou partiel de l'entité.
    """
    node = await find_node(ctx.deps.driver, name)
    if not node:
        return f"Aucune entité ne correspond à « {name} »."
    relations = await all_relations(ctx.deps.driver)
    rel_lines = [
        f"- {r['from']} —[{r['rel_type']}]→ {r['to']}"
        for r in relations
        if node["id"] in (r["from"], r["to"])
    ]
    return (
        f"{node['name']} (id: {node['id']}, type: {node.get('entity_type')})\n"
        f"Propriétés : {fmt_props(node)}\n"
        f"Relations :\n" + ("\n".join(rel_lines) if rel_lines else "—")
    )


async def add_entity(
    ctx: RunContext[GenericDeps],
    name: str,
    entity_type: str,
    props: dict[str, str] | None = None,
) -> str:
    """Crée une nouvelle entité dans la base.

    À appeler uniquement pour une chose qui n'existe pas encore. Pour ajouter
    des informations à une entité existante, utiliser update_entity.

    Args:
        name: Nom de l'entité tel que donné par l'utilisateur (ex: 'marteau XP-55').
        entity_type: Type de l'entité — RÉUTILISER un type existant du schéma si
            le sens correspond, sinon en créer un (minuscules, singulier).
        props: Propriétés factuelles données par l'utilisateur. RÉUTILISER les
            noms de propriétés existants du schéma quand le sens correspond.
    """
    entity_id = slugify(name)
    if not entity_id:
        return f"Nom invalide : « {name} »."
    if await find_node(ctx.deps.driver, entity_id):
        return f"« {name} » existe déjà (id: {entity_id}) — utilise update_entity."

    clean = {k: v for k, v in (props or {}).items() if k not in RESERVED_KEYS}
    async with ctx.deps.driver.session() as session:
        await session.run(
            "MERGE (e:GenEntity {id: $id})"
            " ON CREATE SET e.name = $name, e.entity_type = $type"
            " SET e += $props",
            id=entity_id, name=name, type=entity_type, props=clean,
        )
    ctx.deps.ui_events.append(
        ToolCard(title="Entité créée", subject=name, field=entity_type,
                 added=fmt_props(clean, skip_reserved=False))
    )
    ctx.deps.write_log.append(
        f"création de {entity_id} (type {entity_type}) : {fmt_props(clean, skip_reserved=False)}"
    )
    ctx.deps.touched_ids.add(entity_id)
    return f"Entité créée : {name} (id: {entity_id}, type: {entity_type})."


async def update_entity(
    ctx: RunContext[GenericDeps], name: str, props: dict[str, str]
) -> str:
    """Ajoute ou met à jour des propriétés d'une entité existante.

    Args:
        name: Nom ou id de l'entité existante.
        props: Propriétés à poser. RÉUTILISER les noms de propriétés existants
            du schéma quand le sens correspond (ne pas créer de synonyme).
    """
    node = await find_node(ctx.deps.driver, name)
    if not node:
        return f"« {name} » n'existe pas — utilise add_entity pour la créer."
    clean = {k: v for k, v in props.items() if k not in RESERVED_KEYS}

    # Journal du delta AVANT application — un écrasement de valeur est une
    # information que le check de cohérence doit voir (finding round 1).
    replaced = []
    for key, value in clean.items():
        old = node.get(key)
        if old is not None and str(old) != str(value):
            ctx.deps.write_log.append(f"{node['id']}.{key} : {old!r} REMPLACÉ PAR {value!r}")
            replaced.append(f"{key} (remplaçait : {old!r})")
        else:
            ctx.deps.write_log.append(f"{node['id']}.{key} = {value!r} (nouveau)")

    async with ctx.deps.driver.session() as session:
        await session.run(
            "MATCH (e:GenEntity {id: $id}) SET e += $props",
            id=node["id"], props=clean,
        )
    ctx.deps.ui_events.append(
        ToolCard(title="Entité mise à jour", subject=node["name"],
                 field=node.get("entity_type", "?"),
                 added=fmt_props(clean, skip_reserved=False))
    )
    ctx.deps.touched_ids.add(node["id"])
    suffix = f" — attention, valeurs remplacées : {', '.join(replaced)}" if replaced else ""
    return f"{node['name']} mis à jour : {fmt_props(clean, skip_reserved=False)}.{suffix}"


async def add_relation(
    ctx: RunContext[GenericDeps],
    from_name: str,
    to_name: str,
    rel_type: str,
    props: dict[str, str] | None = None,
) -> str:
    """Crée une relation orientée entre deux entités existantes.

    Args:
        from_name: Nom de l'entité source.
        to_name: Nom de l'entité cible.
        rel_type: Type de la relation (minuscules, ex: 'pose_sur', 'gerant_de') —
            RÉUTILISER un type existant du schéma si le sens correspond.
        props: Propriétés factuelles de la relation (ex: date).
    """
    a = await find_node(ctx.deps.driver, from_name)
    b = await find_node(ctx.deps.driver, to_name)
    if not a or not b:
        missing = from_name if not a else to_name
        return f"« {missing} » n'existe pas — crée d'abord l'entité avec add_entity."
    async with ctx.deps.driver.session() as session:
        await session.run(
            """
            MATCH (a:GenEntity {id: $a}), (b:GenEntity {id: $b})
            MERGE (a)-[r:REL {rel_type: $t}]->(b)
            SET r += $props
            """,
            a=a["id"], b=b["id"], t=rel_type, props=props or {},
        )
    ctx.deps.ui_events.append(
        ToolCard(tool="people", title="Relation ajoutée", subject=a["name"],
                 field=rel_type, added=b["name"])
    )
    extra = f" ({fmt_props(props, skip_reserved=False)})" if props else ""
    ctx.deps.write_log.append(f"relation {a['id']} —[{rel_type}]→ {b['id']}{extra}")
    ctx.deps.touched_ids.add(a["id"])
    ctx.deps.touched_ids.add(b["id"])
    return f"Relation : {a['name']} —[{rel_type}]→ {b['name']}."
