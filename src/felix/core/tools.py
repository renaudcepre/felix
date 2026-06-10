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
    find_non_event,
    fmt_props,
    rename_or_merge,
    touch_entities,
)
from felix.core.models import RelationRef, ToolCard
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
    # Une lecture RÉSOLUE compte dans le working set : l'entité qu'on consulte fait
    # partie de l'histoire en cours (cf. recent_entities).
    await touch_entities(ctx.deps.driver, [node["id"]])
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
    # Garde de coordination : quand le domaine gère une chronologie (manages_events),
    # le type 'evenement' est RÉSERVÉ à add_event (ordre/NEXT). Le créer ici en
    # entité plate produirait un node hors-chaîne. Refus best-effort (retour normal,
    # pas d'erreur d'outil → l'agent passe à autre chose, pas de boucle).
    prof = ctx.deps.profile
    if (prof is not None and prof.manages_events
            and entity_type.strip().lower() in {"evenement", "événement", "évènement", "event"}):
        return (f"« {entity_type} » est un type réservé : une action/un événement ne "
                f"s'enregistre pas comme entité (il est tenu à part dans la chronologie). "
                f"Garde « {name} » pour une vraie entité (personnage, lieu, objet).")

    # Garde anti-sur-entification (#64) : un état interne n'est pas une chose du
    # monde — en nœud, toute relation vers lui devient un non-sens (« Ossian
    # KNOWS dépression »). Le modèle s'auto-étiquette (« maladie », « état ») :
    # on attrape ces types-là au write, la consigne prompt seule ne tient pas.
    if entity_type.strip().lower() in {
        "etat", "état", "maladie", "sentiment", "emotion", "émotion", "humeur",
    }:
        return (f"« {entity_type} » n'est pas un type d'entité : un état interne se "
                f"pose en PROPRIÉTÉ de la fiche concernée (update_entity, ex. clé "
                f"`etat`), jamais en entité ni en relation.")

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
                 added=fmt_props(clean, skip_reserved=False), entity_id=entity_id)
    )
    ctx.deps.write_log.append(
        f"création de {entity_id} (type {entity_type}) : {fmt_props(clean, skip_reserved=False)}"
    )
    ctx.deps.touched_ids.add(entity_id)
    await touch_entities(ctx.deps.driver, [entity_id])
    return f"Entité créée : {name} (id: {entity_id}, type: {entity_type})."


def plan_property_update(
    existing: dict, props: dict[str, str], *, is_correction: bool
) -> tuple[dict[str, str], list[str]]:
    """Partitionne les props d'un update_entity : ce qu'on APPLIQUE vs ce qu'on BLOQUE.

    Règle (cf. SYSTEM_PROMPT 4) : on n'ÉCRASE JAMAIS une valeur existante non-vide par
    une valeur différente — SAUF correction explicite de l'auteur (``is_correction``).
    Une clé NOUVELLE, une valeur IDENTIQUE, ou une clé vide/absente passent toujours
    (enrichissement additif). Bloquer l'écrasement empêche qu'une action du beat
    (« sourit », « ferme les yeux ») détruise un trait durable. Pur → testable sans Neo4j.
    """
    to_set: dict[str, str] = {}
    blocked: list[str] = []
    for key, value in props.items():
        old = existing.get(key)
        overwrites = old is not None and str(old) != "" and str(old) != str(value)
        if overwrites and not is_correction:
            blocked.append(key)
        else:
            to_set[key] = value
    return to_set, blocked


def check_update_target(node: dict | None, name: str) -> str | None:
    """Vérifie que le nœud cible d'update_entity est une vraie entité (non-événement).

    Retourne None si la mise à jour peut se faire, ou un message guidant
    (chaîne, PAS une exception → l'agent rejoue sans boucle ModelRetry).
    Un nœud ``entity_type='evenement'`` est TOUJOURS rejeté : ses données
    appartiennent à la chronologie (add_event), jamais à update_entity.
    Pur → testable sans Neo4j.
    """
    if node is None:
        return f"« {name} » n'existe pas — utilise add_entity pour la créer."
    if node.get("entity_type") == "evenement":
        return (f"« {name} » est un événement, pas une entité — "
                f"crée d'abord l'entité avec add_entity.")
    return None


async def update_entity(
    ctx: RunContext[GenericDeps], name: str, props: dict[str, str],
    is_correction: bool = False,
) -> str:
    """Ajoute ou met à jour des propriétés d'une entité existante.

    N'ÉCRASE PAS une valeur déjà posée : une action qui se passe est un ÉVÉNEMENT (pas
    une propriété), et un fait durable nouveau se range sous une AUTRE clé. Ne mets
    ``is_correction=True`` que si l'auteur CORRIGE explicitement une valeur (« en fait »,
    « plutôt », « correction ») — alors seulement l'ancienne valeur est remplacée.

    Args:
        name: Nom ou id de l'entité existante.
        props: Propriétés à poser. RÉUTILISER les noms de propriétés existants
            du schéma quand le sens correspond (ne pas créer de synonyme).
        is_correction: True UNIQUEMENT pour une correction explicite de l'auteur
            (autorise alors le remplacement d'une valeur existante).
    """
    node = await find_node(ctx.deps.driver, name)
    # Garde anti-événement : find_node peut résoudre sur un nœud evenement quand
    # le name de l'événement contient le nom cherché (ex. « L'Aumônier dit… »).
    guard = check_update_target(node, name)
    if guard is not None:
        return guard
    assert node is not None  # check_update_target retourne None ssi node n'est pas None
    clean = {k: v for k, v in props.items() if k not in RESERVED_KEYS}
    to_set, blocked = plan_property_update(node, clean, is_correction=is_correction)

    # Journal du delta AVANT application — un écrasement (de correction) est une
    # information que le check de cohérence doit voir (finding round 1).
    replaced = []
    for key, value in to_set.items():
        old = node.get(key)
        if old is not None and str(old) != "" and str(old) != str(value):
            ctx.deps.write_log.append(
                f"{node['id']}.{key} : {old!r} REMPLACÉ PAR {value!r} (correction)")
            replaced.append(f"{key} (remplaçait : {old!r})")
        else:
            ctx.deps.write_log.append(f"{node['id']}.{key} = {value!r} (nouveau)")

    if to_set:
        async with ctx.deps.driver.session() as session:
            await session.run(
                "MATCH (e:GenEntity {id: $id}) SET e += $props",
                id=node["id"], props=to_set,
            )
        ctx.deps.ui_events.append(
            ToolCard(title="Entité mise à jour", subject=node["name"],
                     field=node.get("entity_type", "?"),
                     added=fmt_props(to_set, skip_reserved=False), entity_id=node["id"])
        )
        ctx.deps.touched_ids.add(node["id"])
        await touch_entities(ctx.deps.driver, [node["id"]])
        # Un ÉCRASEMENT (correction) peut masquer une contradiction → candidat au check.
        # Une prop purement additive, non (rien à contredire).
        if replaced:
            ctx.deps.check_candidates.add(node["id"])

    # Écrasement refusé : message GUIDANT (pas d'exception → pas de boucle ModelRetry).
    if blocked:
        keys = ", ".join(f"« {k} »" for k in blocked)
        guide = (
            f"Je n'écrase pas {keys} (déjà renseigné). Si c'est une action qui se passe, "
            f"c'est un ÉVÉNEMENT (pas une propriété) ; si c'est un fait DURABLE nouveau, "
            f"range-le sous une AUTRE clé ; si l'auteur corrige explicitement, rappelle "
            f"update_entity avec is_correction=true."
        )
        if to_set:
            return f"{node['name']} : {fmt_props(to_set, skip_reserved=False)} ajouté. {guide}"
        return guide

    suffix = f" — valeurs corrigées : {', '.join(replaced)}" if replaced else ""
    return f"{node['name']} mis à jour : {fmt_props(to_set, skip_reserved=False)}.{suffix}"


async def rename_entity(
    ctx: RunContext[GenericDeps], current_name: str, new_name: str
) -> str:
    """Renomme une entité existante — ou la FUSIONNE si `new_name` désigne déjà une AUTRE
    entité.

    À utiliser quand l'auteur NOMME une entité qu'on suivait sans vrai nom (« le pêcheur
    s'appelle Joseph ») ou quand deux fiches sont en réalité la même chose (« Veil, c'est
    l'homme de main »). Les relations et les événements suivent AUTOMATIQUEMENT, rien
    n'est perdu. NE crée PAS une nouvelle fiche pour une entité déjà suivie : renomme-la.

    Args:
        current_name: Nom ou id de l'entité existante (y compris un nom provisoire).
        new_name: Le nom à lui donner.
    """
    # La mécanique (migration d'id, fusion sur collision) vit au niveau driver
    # (graph.rename_or_merge) : la route PATCH de l'API (#61) DOIT avoir le même
    # effet qu'ici. Le tool ne garde que le narratif (cartes, write_log, working set).
    node = await find_node(ctx.deps.driver, current_name)
    if not node:
        return f"« {current_name} » n'existe pas — rien à renommer."
    out = await rename_or_merge(ctx.deps.driver, current_name, new_name)

    if out.status == "invalid":
        return f"Nom invalide : « {new_name} »."

    if out.status == "refreshed":
        ctx.deps.touched_ids.add(out.final_id)
        await touch_entities(ctx.deps.driver, [out.final_id])
        return f"« {out.old_name} » est désormais « {new_name} »."

    if out.status == "merged":
        ctx.deps.ui_events.append(
            ToolCard(title="Fiches fusionnées", subject=out.old_name,
                     field=out.new_name, added="relations et événements conservés",
                     entity_id=out.final_id)
        )
        ctx.deps.write_log.append(f"fusion {node['id']} → {out.final_id}")
        ctx.deps.touched_ids.add(out.final_id)
        await touch_entities(ctx.deps.driver, [out.final_id])
        ctx.deps.check_candidates.add(out.final_id)
        return (f"« {out.old_name} » et « {out.new_name} » étaient la même entité — "
                f"fusionnées dans « {out.new_name} » (relations et événements conservés).")

    ctx.deps.ui_events.append(
        ToolCard(title="Entité renommée", subject=out.old_name,
                 field=node.get("entity_type", "?"), added=f"→ {new_name}",
                 entity_id=out.final_id)
    )
    ctx.deps.write_log.append(f"renommage {node['id']} → {out.final_id} ({new_name})")
    ctx.deps.touched_ids.add(out.final_id)
    await touch_entities(ctx.deps.driver, [out.final_id])
    return f"« {out.old_name} » renommé « {new_name} »."


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
        rel_type: Type de la relation. TOUJOURS un type CANONIQUE du domaine
            (CAPITALES anglaises, ex: LOCATED_AT, FIGHTS, CREATES) listé dans le
            bloc DOMAINE / describe_schema. Si aucun type ne correspond au lien
            réel, n'écris pas de relation : l'information ira dans une propriété
            de fiche, pas dans une arête.
        props: Propriétés factuelles de la relation (ex: date).
    """
    # Résolution HORS événements : une relation entre entités ne doit jamais avoir
    # un node événement pour extrémité (sinon « Vance FIGHTS [event] », « event KNOWS
    # perso »…). Les événements ne se relient qu'via add_event (INVOLVES/NEXT/LOCATED_AT).
    a = await find_non_event(ctx.deps.driver, from_name)
    b = await find_non_event(ctx.deps.driver, to_name)
    if not a or not b:
        missing = from_name if not a else to_name
        return f"« {missing} » n'existe pas — crée d'abord l'entité avec add_entity."

    # Typage du domaine : vocab dur + pas de boucle + domaine/portée (refus des seules
    # violations CLAIRES). Refus = message guidant renvoyé tel quel (pas d'écriture, pas
    # d'exception → l'agent rejoue avec un type/sens valides, sans boucle ModelRetry).
    if ctx.deps.profile is not None:
        problem = ctx.deps.profile.validate_relation(
            rel_type,
            a.get("entity_type", ""),
            b.get("entity_type", ""),
            same_node=a["id"] == b["id"],
        )
        if problem:
            return problem

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
                 field=rel_type, added=b["name"],
                 relation=RelationRef(from_id=a["id"], to_id=b["id"], rel_type=rel_type))
    )
    extra = f" ({fmt_props(props, skip_reserved=False)})" if props else ""
    ctx.deps.write_log.append(f"relation {a['id']} —[{rel_type}]→ {b['id']}{extra}")
    ctx.deps.touched_ids.add(a["id"])
    ctx.deps.touched_ids.add(b["id"])
    await touch_entities(ctx.deps.driver, [a["id"], b["id"]])
    # Les deux extrémités d'une nouvelle relation sont candidates au check
    # (relation = là où vivent les contradictions spatiales/relationnelles).
    ctx.deps.check_candidates.add(a["id"])
    ctx.deps.check_candidates.add(b["id"])
    return f"Relation : {a['name']} —[{rel_type}]→ {b['name']}."


async def add_event(
    ctx: RunContext[GenericDeps],
    resume: str,
    participants: list[str] | None = None,
    lieu: str | None = None,
) -> str:
    """Enregistre un ÉVÉNEMENT du récit : une action qui SE PASSE à un instant donné
    (ex. « Vance tire sur les consoles », « le réacteur explose »).

    À n'utiliser QUE pour ce qui ARRIVE et fait avancer l'histoire — jamais pour un
    état durable (« est ingénieure », « a un bras mécanique ») qui, lui, est une
    PROPRIÉTÉ du personnage (update_entity). Test : « quand ? » a pour réponse un
    instant → événement ; « quand ? » est absurde (ça tient tout le temps) → ce
    n'est pas un événement.

    L'ordre chronologique et le chaînage NEXT sont gérés AUTOMATIQUEMENT : tu n'as
    pas à numéroter, chaque événement se range à la suite du précédent.

    Args:
        resume: Ce qui se passe, en une phrase courte (« Silas examine le cadavre »).
        participants: Noms d'entités EXISTANTES qui prennent part à l'événement
            (personnages, objets) — reliées par INVOLVES.
        lieu: Nom du lieu EXISTANT où ça se passe — relié par LOCATED_AT.
    """
    text = resume.strip()
    if not text:
        return "Résumé d'événement vide — rien enregistré."

    # ordre auto-incrémenté (en code, pas par le modèle) + id unique : deux actions
    # proches ne doivent PAS fusionner, donc surtout pas de slug du résumé. Le lock
    # sérialise les add_event concurrents d'un même run (sinon collision d'ordre/id).
    async with ctx.deps.event_seq_lock, ctx.deps.driver.session() as session:
        # Dédup : ne pas recréer un événement au resume identique (le chroniqueur
        # appelle parfois add_event 2x pour la même action dans une seule réponse).
        dup = await session.run(
            "MATCH (e:GenEntity {entity_type: 'evenement'})"
            " WHERE toLower(e.resume) = toLower($r) RETURN e.id LIMIT 1",
            r=text,
        )
        if await dup.single():
            return f"Événement déjà enregistré (ignoré) : {text}."
        result = await session.run(
            "MATCH (e:GenEntity {entity_type: 'evenement'}) RETURN max(e.ordre) AS maxo"
        )
        record = await result.single()
        prev_ordre = record["maxo"] if record else None
        ordre = (prev_ordre + 1) if prev_ordre is not None else 1
        event_id = f"event-{ordre}"
        await session.run(
            "CREATE (e:GenEntity {id: $id, name: $name, entity_type: 'evenement',"
            " resume: $resume, ordre: $ordre})",
            id=event_id, name=text, resume=text, ordre=ordre,
        )
        # Chaîne NEXT depuis l'événement de plus grand ordre précédent.
        if prev_ordre is not None:
            await session.run(
                "MATCH (p:GenEntity {entity_type: 'evenement', ordre: $po}),"
                " (e:GenEntity {id: $id})"
                " MERGE (p)-[:REL {rel_type: 'NEXT'}]->(e)",
                po=prev_ordre, id=event_id,
            )

    # Participants / lieu : reliés seulement s'ils existent déjà comme VRAIES entités
    # (le chroniqueur ne crée pas d'entité). Résolution restreinte aux NON-événements :
    # sinon un participant nommé comme un résumé matche un node evenement — voire
    # CELUI qu'on vient de créer (même nom) → auto-INVOLVES. Dédupliqué ; jamais soi.
    linked: list[str] = []
    seen_ids: set[str] = {event_id}
    targets = [(p, "INVOLVES") for p in (participants or [])]
    if lieu:
        targets.append((lieu, "LOCATED_AT"))
    for raw, rel in targets:
        node = await find_non_event(ctx.deps.driver, raw)
        if not node or node["id"] in seen_ids:
            continue
        seen_ids.add(node["id"])
        async with ctx.deps.driver.session() as session:
            await session.run(
                "MATCH (e:GenEntity {id: $e}), (t:GenEntity {id: $t})"
                " MERGE (e)-[r:REL {rel_type: $rel}]->(t)",
                e=event_id, t=node["id"], rel=rel,
            )
        linked.append(node["name"])
        ctx.deps.touched_ids.add(node["id"])
        # L'entité IMPLIQUÉE dans un événement est candidate au check (timeline →
        # check temporel « mort puis agit »). Le nœud événement lui-même, non.
        ctx.deps.check_candidates.add(node["id"])

    # Les participants/lieu entrent dans le working set (pas le nœud événement,
    # de toute façon exclu de recent_entities).
    await touch_entities(ctx.deps.driver, seen_ids - {event_id})

    ctx.deps.ui_events.append(
        ToolCard(tool="people", title="Événement", subject=text,
                 field=f"#{ordre}", added=", ".join(linked) or "—", entity_id=event_id)
    )
    ctx.deps.write_log.append(
        f"événement #{ordre} : {text} (participants : {', '.join(linked) or '—'})"
    )
    ctx.deps.touched_ids.add(event_id)
    return f"Événement #{ordre} enregistré : {text} (participants : {', '.join(linked) or '—'})."
