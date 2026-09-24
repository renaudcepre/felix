"""Les 5 tools du noyau générique — lecture/écriture d'entités libres :GenEntity.

Les docstrings portent la DISCIPLINE de schéma émergent (réutiliser types et noms
de propriétés existants plutôt que d'en inventer) : c'est par elles que le petit
modèle tient le cap, pas par du code. Ne pas les diluer.
"""
from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

from pydantic_ai import RunContext

from felix.core.deps import GenericDeps

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from felix.core.profile import Profile

from felix.core.graph import (
    NARRATIVE_REL,
    REL_RESERVED_KEYS,
    RESERVED_KEYS,
    all_entities,
    all_relations,
    create_entity,
    find_node,
    find_non_event,
    fmt_props,
    rel_label,
    rename_or_merge,
    touch_entities,
)
from felix.core.models import PropChange, RelationRef, ToolCard
from felix.core.schema_detector import content_tokens, verb_head
from felix.ingest.resolver import slugify

# ─────────────────────────── Helpers réordonnancement (#44) ─────────────────

_RESUME_PREVIEW = 40  # longueur max d'un aperçu de résumé dans les cartes / logs


def _norm(text: str) -> str:
    """Lowercase + suppression des accents (NFKD) pour la résolution de fragments."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _list_resumes(events: list[dict], limit: int = 15) -> str:
    """Liste numérotée des résumés (ordre diégétique), pour les messages de refus.

    Sans elle, le modèle s'entête : il dit naturellement « la mort de X » quand le
    résumé en base dit « X meurt » (nominalisation vs verbe), le refus sec le fait
    re-tenter en variations jusqu'au request_limit (vécu : UsageLimitExceeded à 50).
    Donner les résumés exacts n'est PAS un contournement façon #59 (qui vise les
    interdictions SÉMANTIQUES) : c'est l'information factuelle du 2e essai."""
    shown = events[:limit]
    lines = " ; ".join(f"({e['ordre']}) {e['resume']}" for e in shown)
    suffix = f" ; … (+{len(events) - limit})" if len(events) > limit else ""
    return lines + suffix


def resolve_event_fragment(
    events: list[dict], fragment: str
) -> tuple[dict | None, str | None]:
    """Résout un fragment de résumé vers un événement existant.

    Matching insensible à la casse et aux accents sur le champ ``resume``.

    Returns:
        (event, None) si match unique ;
        (None, message_refus) si zéro ou plus d'un match — refus SANS effet
        (pas d'insertion, pas de déplacement), mais le message LISTE les résumés
        disponibles pour que le modèle cite un fragment exact au 2e essai.
    """
    norm_frag = _norm(fragment)
    matches = [
        e for e in events
        if norm_frag in _norm(str(e.get("resume", "")))
    ]
    if len(matches) == 0:
        return None, (
            f"référence introuvable — aucun événement ne contient « {fragment} ». "
            f"Événements connus : {_list_resumes(events)}. "
            "Rien n'a été inséré ni déplacé : ré-appelle en citant les mots EXACTS "
            "d'un de ces résumés."
        )
    if len(matches) > 1:
        return None, (
            f"référence ambiguë — {len(matches)} événements contiennent « {fragment} » : "
            f"{_list_resumes(matches)}. "
            "Rien n'a été inséré ni déplacé : ré-appelle avec un fragment plus précis."
        )
    return matches[0], None


def compute_insert_before(
    ordered_ids: list[str], new_id: str, ref_id: str
) -> list[str]:
    """Retourne la liste avec ``new_id`` inséré AVANT ``ref_id``.

    Pure (sans effet de bord) — testable sans Neo4j.
    """
    idx = ordered_ids.index(ref_id)
    return [*ordered_ids[:idx], new_id, *ordered_ids[idx:]]


def compute_move_before(
    ordered_ids: list[str], event_id: str, ref_id: str
) -> list[str]:
    """Retourne la liste avec ``event_id`` déplacé AVANT ``ref_id``.

    Pure (sans effet de bord) — testable sans Neo4j.
    """
    without = [i for i in ordered_ids if i != event_id]
    idx = without.index(ref_id)
    return [*without[:idx], event_id, *without[idx:]]


def compute_move_after(
    ordered_ids: list[str], event_id: str, ref_id: str
) -> list[str]:
    """Retourne la liste avec ``event_id`` déplacé APRÈS ``ref_id``.

    Pure (sans effet de bord) — testable sans Neo4j.
    """
    without = [i for i in ordered_ids if i != event_id]
    idx = without.index(ref_id)
    return [*without[:idx + 1], event_id, *without[idx + 1:]]


async def _rebuild_event_sequence(
    driver: AsyncDriver, proj: str, ordered_ids: list[str]
) -> None:
    """Réassigne les ordres 1..N et recoud la chaîne NEXT pour un projet.

    ``ordered_ids`` est l'ordre CIBLE (ids des événements dans l'ordre diégétique
    voulu). Opération REBUILD complet : suppression de toutes les arêtes NEXT
    existantes entre événements du projet, réécriture des ordres, recréation du
    chemin. La simplicité prime sur la performance (volumes locaux, dizaines d'events).

    Toutes les requêtes scopées ``project`` (#60). Chaque requête ouvre sa propre
    session (pattern codebase) pour éviter les conflits de pipelining Neo4j.
    """
    # 1. Supprimer toutes les arêtes NEXT entre events du projet
    async with driver.session() as session:
        await session.run(
            "MATCH (a:GenEntity {entity_type: 'evenement', project: $project})"
            "-[r:REL {rel_type: 'NEXT'}]->"
            "(b:GenEntity {entity_type: 'evenement', project: $project})"
            " DELETE r",
            project=proj,
        )
    # 2. Réassigner les ordres 1..N
    for i, eid in enumerate(ordered_ids, start=1):
        async with driver.session() as session:
            await session.run(
                "MATCH (e:GenEntity {id: $id, project: $project}) SET e.ordre = $ordre",
                id=eid, ordre=i, project=proj,
            )
    # 3. Recoudre la chaîne NEXT
    for i in range(len(ordered_ids) - 1):
        async with driver.session() as session:
            await session.run(
                "MATCH (a:GenEntity {id: $a, project: $project}),"
                " (b:GenEntity {id: $b, project: $project})"
                " MERGE (a)-[:REL {rel_type: 'NEXT'}]->(b)",
                a=ordered_ids[i], b=ordered_ids[i + 1], project=proj,
            )


async def describe_schema(ctx: RunContext[GenericDeps]) -> str:
    """Décrit le schéma actuel de la base : types d'entités, noms de propriétés
    et types de relations déjà utilisés.

    À appeler AVANT toute écriture, pour réutiliser les types et noms de
    propriétés existants au lieu d'en inventer de nouveaux.
    """
    entities = await all_entities(ctx.deps.driver, project=ctx.deps.project_id)
    relations = await all_relations(ctx.deps.driver, project=ctx.deps.project_id)
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
    # Verbes narratifs déjà posés : les montrer incite à RÉUTILISER le même verbe
    # pour le même lien (la clé de dédup est le slug du verbe, cf. add_relation).
    verbs = sorted(
        {str(r["props"].get("verbe", "")).strip() for r in relations
         if r["rel_type"] == NARRATIVE_REL} - {""}
    )
    if verbs:
        lines.append(f"Verbes {NARRATIVE_REL} déjà utilisés : {', '.join(verbs)}")
    return "\n".join(lines)


async def list_entities(ctx: RunContext[GenericDeps]) -> str:
    """Liste toutes les entités de la base (nom + type), groupées par type.

    À appeler pour répondre à une question sur le CONTENU de la base (« qu'y
    a-t-il ? », « qui sont les personnages ? ») ou pour voir ce qui existe déjà
    avant de créer. Ne devine jamais le contenu : lis-le ici.
    """
    entities = await all_entities(ctx.deps.driver, project=ctx.deps.project_id)
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
    node = await find_node(ctx.deps.driver, name, project=ctx.deps.project_id)
    if not node:
        return f"Aucune entité ne correspond à « {name} »."
    # Une lecture RÉSOLUE compte dans le working set : l'entité qu'on consulte fait
    # partie de l'histoire en cours (cf. recent_entities).
    await touch_entities(ctx.deps.driver, [node["id"]], project=ctx.deps.project_id)
    relations = await all_relations(ctx.deps.driver, project=ctx.deps.project_id)
    rel_lines = [
        f"- {r['from']} —[{rel_label(r)}]→ {r['to']}"
        for r in relations
        if node["id"] in (r["from"], r["to"])
    ]
    return (
        f"{node['name']} (id: {node['id']}, type: {node.get('entity_type')})\n"
        f"Propriétés : {fmt_props(node)}\n"
        f"Relations :\n" + ("\n".join(rel_lines) if rel_lines else "—")
    )


def check_add_entity_guards(
    name: str,
    entity_type: str,
    refused_names: set[str],
    profile: Profile | None,
) -> tuple[str | None, bool]:
    """Gardes sémantiques pures de add_entity — testables sans Neo4j.

    Retourne (message_de_refus | None, ajouter_au_refused_names).

    Trois cas de refus, dans cet ordre :
    1. Garde mémoire de tour : le slug du nom est déjà dans refused_names →
       refus terminal court, False (déjà enregistré, rien à ajouter).
    2. Garde type réservé : entity_type='evenement' sur un profil manages_events →
       refus terminal, True (ajouter le slug pour bloquer toute re-tentative).
    3. Garde anti-sur-entification (#64) : entity_type dans {état, maladie, …} →
       refus guidant (pointe update_entity), True.

    Garde symbolique > consigne (leçons #48/#64 : la consigne seule ne tient pas
    sur Small). Les messages de refus sont TERMINAUX — ils ne listent plus de types
    alternatifs pour ne plus servir de guide de contournement.
    """
    slug = slugify(name)
    etype_low = entity_type.strip().lower()

    # 1. Garde mémoire : nom déjà refusé ce tour, quel que soit le type proposé.
    if slug in refused_names:
        return (
            f"« {name} » a déjà été refusé ce tour — n'enregistre pas cet élément"
            f" sous aucun type.",
            False,
        )

    # 2. Garde type réservé : evenement
    if (profile is not None and profile.manages_events
            and etype_low in {"evenement", "événement", "évènement", "event"}):
        return (
            f"« {entity_type} » est un type réservé : un événement appartient à la "
            f"chronologie (add_event), pas au graphe d'entités. N'enregistre pas "
            f"« {name} » comme entité ce tour-ci, sous aucun autre type.",
            True,
        )

    # 3. Garde anti-sur-entification (#64)
    if etype_low in {
        "etat", "état", "maladie", "sentiment", "emotion", "émotion", "humeur",
    }:
        return (
            f"« {entity_type} » n'est pas un type d'entité : un état interne se "
            f"pose en PROPRIÉTÉ de la fiche concernée (update_entity, ex. clé "
            f"`etat`), jamais en entité ni en relation. Ne crée pas d'entité pour "
            f"cet état, sous aucun type.",
            True,
        )

    return None, False


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
    # Gardes sémantiques : type réservé, état interne, re-tentative mémorisée.
    # Refus best-effort (retour normal, pas d'exception → pas de boucle ModelRetry).
    msg, add_to_refused = check_add_entity_guards(
        name, entity_type, ctx.deps.refused_names, ctx.deps.profile
    )
    if msg is not None:
        if add_to_refused:
            ctx.deps.refused_names.add(slugify(name))
        return msg

    entity_id = slugify(name)
    if not entity_id:
        return f"Nom invalide : « {name} »."
    if await find_node(ctx.deps.driver, entity_id, project=ctx.deps.project_id):
        return f"« {name} » existe déjà (id: {entity_id}) — utilise update_entity."

    clean = {k: v for k, v in (props or {}).items() if k not in RESERVED_KEYS}
    # Clé composite {id, project} (#60) : deux histoires ont chacune leur
    # « camille » — l'unicité vit dans la clé de MERGE, pas dans une contrainte.
    # create_entity est le chemin PARTAGÉ avec l'ingestion de document EN CODE
    # (#Étape 2) : même forme de nœud, une seule requête.
    await create_entity(
        ctx.deps.driver, entity_id, name, entity_type, clean, project=ctx.deps.project_id,
    )
    ctx.deps.ui_events.append(
        ToolCard(title="Entité créée", subject=name, field=entity_type,
                 added=fmt_props(clean, skip_reserved=False), entity_id=entity_id)
    )
    ctx.deps.write_log.append(
        f"création de {entity_id} (type {entity_type}) : {fmt_props(clean, skip_reserved=False)}"
    )
    ctx.deps.touched_ids.add(entity_id)
    await touch_entities(ctx.deps.driver, [entity_id], project=ctx.deps.project_id)
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
    node = await find_node(ctx.deps.driver, name, project=ctx.deps.project_id)
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
    # `changes` (#72) nourrit la carte : uniquement les vraies MODIFICATIONS
    # (valeur déjà présente ET différente) — jamais un ajout, jamais une valeur
    # reposée à l'identique. `added_only` = le reste de to_set (ajouts/inchangé),
    # pour que la carte n'affiche pas deux fois le même champ.
    replaced = []
    changes: list[PropChange] = []
    added_only: dict[str, str] = {}
    for key, value in to_set.items():
        old = node.get(key)
        if old is not None and str(old) != "" and str(old) != str(value):
            ctx.deps.write_log.append(
                f"{node['id']}.{key} : {old!r} REMPLACÉ PAR {value!r} (correction)")
            replaced.append(f"{key} (remplaçait : {old!r})")
            changes.append(PropChange(field=key, before=str(old), after=str(value)))
        else:
            ctx.deps.write_log.append(f"{node['id']}.{key} = {value!r} (nouveau)")
            added_only[key] = value

    if to_set:
        async with ctx.deps.driver.session() as session:
            await session.run(
                "MATCH (e:GenEntity {id: $id, project: $project}) SET e += $props",
                id=node["id"], props=to_set, project=ctx.deps.project_id,
            )
        ctx.deps.ui_events.append(
            ToolCard(title="Entité mise à jour", subject=node["name"],
                     field=node.get("entity_type", "?"),
                     added=fmt_props(added_only, skip_reserved=False) if added_only else "",
                     changes=changes or None, entity_id=node["id"])
        )
        ctx.deps.touched_ids.add(node["id"])
        await touch_entities(ctx.deps.driver, [node["id"]], project=ctx.deps.project_id)
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
    node = await find_node(ctx.deps.driver, current_name, project=ctx.deps.project_id)
    if not node:
        return f"« {current_name} » n'existe pas — rien à renommer."
    out = await rename_or_merge(
        ctx.deps.driver, current_name, new_name, project=ctx.deps.project_id
    )

    if out.status == "invalid":
        return f"Nom invalide : « {new_name} »."

    if out.status == "refreshed":
        ctx.deps.touched_ids.add(out.final_id)
        await touch_entities(ctx.deps.driver, [out.final_id], project=ctx.deps.project_id)
        return f"« {out.old_name} » est désormais « {new_name} »."

    if out.status == "merged":
        ctx.deps.ui_events.append(
            ToolCard(title="Fiches fusionnées", subject=out.old_name,
                     field=out.new_name, added="relations et événements conservés",
                     entity_id=out.final_id)
        )
        ctx.deps.write_log.append(f"fusion {node['id']} → {out.final_id}")
        ctx.deps.touched_ids.add(out.final_id)
        await touch_entities(ctx.deps.driver, [out.final_id], project=ctx.deps.project_id)
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
    await touch_entities(ctx.deps.driver, [out.final_id], project=ctx.deps.project_id)
    return f"« {out.old_name} » renommé « {new_name} »."


async def retype_entity(
    ctx: RunContext[GenericDeps], name: str, nouveau_type: str
) -> str:
    """Corrige le TYPE d'une entité existante (« le Klarkz n'est pas un lieu,
    c'est un minerai » → retype_entity('Klarkz', 'objet')).

    À utiliser quand l'auteur dit qu'une entité a été rangée sous le mauvais type.
    Ne touche ni au nom, ni aux propriétés, ni aux relations — mais signale les
    relations que le nouveau type rend douteuses, sans les supprimer.

    Args:
        name: Nom ou id de l'entité existante.
        nouveau_type: Le type corrigé (ex: objet, lieu, groupe, personnage).
    """
    node = await find_non_event(ctx.deps.driver, name, project=ctx.deps.project_id)
    if not node:
        return f"« {name} » n'existe pas — rien à retyper."

    ancien = str(node.get("entity_type", "?"))
    nouveau = nouveau_type.strip()
    if nouveau.lower() == ancien.lower():
        return f"« {node['name']} » est déjà de type {ancien} — rien à faire."

    # Les gardes de CRÉATION sont rejouées sur le type cible (#75) : retyper vers
    # `evenement` ou un état (#64) serait le même contournement qu'une création.
    # On n'inscrit PAS le nom dans refused_names : l'entité existe et reste
    # légitime sous son type actuel — seul le retypage est refusé.
    refusal, _ = check_add_entity_guards(
        node["name"], nouveau, set(), ctx.deps.profile
    )
    if refusal:
        return refusal

    async with ctx.deps.driver.session() as session:
        await session.run(
            "MATCH (e:GenEntity {id: $id, project: $project})"
            " SET e.entity_type = $type",
            id=node["id"], type=nouveau, project=ctx.deps.project_id,
        )
        # Re-valider les arêtes STRUCTURELLES sous le nouveau type : celles que
        # le retypage rend invalides (domaine/portée) sont SIGNALÉES, jamais
        # supprimées — l'auteur ou le checker tranchera (témoignage).
        result = await session.run(
            """
            MATCH (e:GenEntity {id: $id, project: $project})-[r:REL]-(o:GenEntity)
            WHERE r.rel_type IS NOT NULL
              AND NOT r.rel_type IN ['LIE_A', 'NEXT', 'INVOLVES']
            RETURN r.rel_type AS t, startNode(r) = e AS outgoing,
                   o.entity_type AS otype, o.name AS oname
            """,
            id=node["id"], project=ctx.deps.project_id,
        )
        edges = [r.data() async for r in result]

    doubtful: list[str] = []
    if ctx.deps.profile is not None:
        for e in edges:
            from_t = nouveau if e["outgoing"] else str(e["otype"] or "")
            to_t = str(e["otype"] or "") if e["outgoing"] else nouveau
            problem = ctx.deps.profile.validate_relation(
                e["t"], from_t, to_t, same_node=False, verbe="",
            )
            if problem:
                arrow = f"{node['name']} —[{e['t']}]→ {e['oname']}" if e["outgoing"] \
                    else f"{e['oname']} —[{e['t']}]→ {node['name']}"
                doubtful.append(arrow)

    ctx.deps.ui_events.append(
        ToolCard(title="Type corrigé", subject=node["name"],
                 field=ancien, added=f"→ {nouveau}", entity_id=node["id"])
    )
    ctx.deps.write_log.append(f"retypage {node['id']} : {ancien} → {nouveau} (correction)")
    ctx.deps.touched_ids.add(node["id"])
    await touch_entities(ctx.deps.driver, [node["id"]], project=ctx.deps.project_id)
    # Le checker doit revoir l'entité : c'est lui qui alertait tant que le type
    # était faux — l'alerte s'éteint par construction une fois le type corrigé.
    ctx.deps.check_candidates.add(node["id"])

    msg = f"« {node['name']} » est désormais de type {nouveau} (était : {ancien})."
    if doubtful:
        msg += (
            " Attention, ce nouveau type rend douteuse(s) : "
            + " ; ".join(doubtful)
            + ". Rien n'a été supprimé — signale-le à l'auteur si pertinent."
        )
    return msg


_MIN_HEAD_PREFIX_LEN = 4  # sous ce seuil un préfixe partagé est trop court pour être significatif


def _same_head_or_prefix(a: str, b: str) -> bool:
    """Vrai si `a` et `b` sont la MÊME tête, ou si la plus courte est un préfixe
    de la plus longue (accord masculin/féminin, verbe/infinitif : « regle » est
    un préfixe de « regler », « concerne » un préfixe de « concernee »). Le
    garde-fou de longueur évite qu'une tête très courte matche n'importe quoi."""
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= _MIN_HEAD_PREFIX_LEN and longer.startswith(shorter)


def same_narrative_link(new_verb: str, existing_verbs: list[str]) -> bool:
    """Vrai si `new_verb` désigne le MÊME lien narratif (LIE_A) qu'un des
    `existing_verbs` — une PARAPHRASE, pas un autre lien. Garde de add_relation
    contre le bug vu en live : le même fait re-décrit avec des mots différents
    (« concerné par » PUIS « Machine concernée ») crée deux arêtes au lieu d'une.

    Comparaison sur la TÊTE du verbe (``verb_head``, cf. schema_detector) :
    même tête → même lien. Sinon, la tête de l'un est comparée à CHAQUE token
    substantiel de l'autre (``content_tokens``) — nécessaire car la tête ne
    retient que le PREMIER token substantiel : « Machine concernée » a pour
    tête « machine », mais c'est son second token, « concernee », qui se
    rapproche de « concerne » (tête de « concerné par »). Une tête préfixe
    d'un token (dans un sens OU l'autre, cf. ``_same_head_or_prefix``) compte
    comme la même tête (accord, verbe/infinitif).

    Deux verbes de sens clairement différents (« règle » / « signale »,
    « lance » / « arrête ») rendent False : deux arêtes distinctes restent
    légitimes. Pure, testable sans Neo4j.
    """
    new_head = verb_head(new_verb)
    if not new_head:
        return False
    new_tokens = content_tokens(new_verb)
    for existing in existing_verbs:
        old_head = verb_head(existing)
        if not old_head:
            continue
        if _same_head_or_prefix(new_head, old_head):
            return True
        old_tokens = content_tokens(existing)
        if any(_same_head_or_prefix(new_head, t) for t in old_tokens):
            return True
        if any(_same_head_or_prefix(old_head, t) for t in new_tokens):
            return True
    return False


async def add_relation(  # noqa: PLR0913 — `verbe` est un param EXPLICITE, pas une prop enfouie (#68)
    ctx: RunContext[GenericDeps],
    from_name: str,
    to_name: str,
    rel_type: str,
    verbe: str = "",
    props: dict[str, str] | None = None,
) -> str:
    """Crée une relation orientée entre deux entités existantes.

    Args:
        from_name: Nom de l'entité source.
        to_name: Nom de l'entité cible.
        rel_type: Type de la relation. Un type STRUCTUREL du domaine (CAPITALES
            anglaises, ex: LOCATED_AT, MEMBER_OF, PART_OF — liste exacte dans le
            bloc DOMAINE / describe_schema), ou LIE_A pour TOUT AUTRE lien réel
            du texte (avec le paramètre verbe). N'écris une relation que si le
            texte pose le lien.
        verbe: REQUIS avec rel_type=LIE_A : les mots EXACTS de l'auteur pour ce
            lien (ex: 'était la maîtresse de', 'fait chanter'). Ne traduis pas,
            ne résume pas. Ignoré pour un type structurel.
        props: Propriétés factuelles de la relation (ex: date).
    """
    # Résolution HORS événements : une relation entre entités ne doit jamais avoir
    # un node événement pour extrémité (sinon « Vance [se bat contre] [event] »…).
    # Les événements ne se relient qu'via add_event (INVOLVES/NEXT/LOCATED_AT).
    # Relations réservées AU CODE (ex. DESCRIBED_IN, posée par l'ingestion de
    # document, #Étape 2) : refusée AVANT toute résolution d'entité — le modèle
    # n'a pas à savoir si les extrémités existent pour comprendre que ce type
    # ne lui appartient pas.
    if ctx.deps.profile is not None and rel_type in ctx.deps.profile.code_only_relations:
        return (
            f"« {rel_type} » est posée automatiquement par le code, n'y touche pas."
        )

    a = await find_non_event(ctx.deps.driver, from_name, project=ctx.deps.project_id)
    b = await find_non_event(ctx.deps.driver, to_name, project=ctx.deps.project_id)
    if not a or not b:
        missing = from_name if not a else to_name
        return f"« {missing} » n'existe pas — crée d'abord l'entité avec add_entity."

    # Typage du domaine : noyau structurel dur (domaine/portée, refus des seules
    # violations CLAIRES) + canal narratif (verbe verbatim requis). Refus = message
    # guidant renvoyé tel quel (pas d'écriture, pas d'exception → l'agent rejoue
    # avec un type/sens valides, sans boucle ModelRetry).
    if ctx.deps.profile is not None:
        problem = ctx.deps.profile.validate_relation(
            rel_type,
            a.get("entity_type", ""),
            b.get("entity_type", ""),
            same_node=a["id"] == b["id"],
            verbe=verbe,
        )
        if problem:
            return problem

    # `props` libres ne peuvent pas écraser les clés posées en code.
    props = {k: v for k, v in (props or {}).items() if k not in REL_RESERVED_KEYS}
    verbe = verbe.strip()
    narrative = rel_type == NARRATIVE_REL and bool(verbe)

    if narrative:
        # Garde anti-paraphrase (bug vu en live sur une fiche réelle) : AVANT
        # d'écrire, si la paire porte déjà un LIE_A — dans N'IMPORTE QUELLE
        # direction — avec un verbe DIFFÉRENT que same_narrative_link juge être
        # le MÊME lien (« concerné par » / « Machine concernée »), on refuse
        # plutôt que de poser une 2e arête pour le même fait. Le verbe re-émis
        # À L'IDENTIQUE (même verbe_slug) n'entre PAS ici : il suit le chemin
        # normal ci-dessous, silencieux par le mécanisme #45.
        async with ctx.deps.driver.session() as session:
            existing_result = await session.run(
                """
                MATCH (a:GenEntity {id: $a, project: $project})
                      -[r:REL {rel_type: $t}]-
                      (b:GenEntity {id: $b, project: $project})
                RETURN DISTINCT r.verbe AS verbe, r.verbe_slug AS verbe_slug
                """,
                a=a["id"], b=b["id"], t=rel_type, project=ctx.deps.project_id,
            )
            existing_rows = [dict(r) for r in await existing_result.data()]
        new_slug = slugify(verbe)
        other_verbs = sorted({
            str(row["verbe"]) for row in existing_rows
            if row["verbe_slug"] != new_slug and row["verbe"]
        })
        if other_verbs and same_narrative_link(verbe, other_verbs):
            listed = ", ".join(f"« {v} »" for v in other_verbs)
            return (
                f"Un lien existe déjà entre {a['name']} et {b['name']} : {listed}. "
                "Si c'est le même lien, n'écris rien ; si c'est vraiment un AUTRE "
                "lien, choisis un verbe dont le sens diffère clairement (pas une "
                "reformulation)."
            )

    async with ctx.deps.driver.session() as session:
        if narrative:
            # Clé de MERGE = (paire, slug du verbe) : deux liens différents entre
            # la même paire (aime ET commande) = deux arêtes ; le même verbe
            # re-extrait ne duplique pas (#68). `existed` détecte la ré-émission
            # AVANT le MERGE (#45 : 3 moteurs ré-émettent l'existant chaque tour).
            result = await session.run(
                """
                MATCH (a:GenEntity {id: $a, project: $project}),
                      (b:GenEntity {id: $b, project: $project})
                OPTIONAL MATCH (a)-[e:REL {rel_type: $t, verbe_slug: $vs}]->(b)
                WITH a, b, e IS NOT NULL AS existed
                MERGE (a)-[r:REL {rel_type: $t, verbe_slug: $vs}]->(b)
                SET r.verbe = $verbe, r += $props
                RETURN existed
                """,
                a=a["id"], b=b["id"], t=rel_type, vs=slugify(verbe),
                verbe=verbe, props=props, project=ctx.deps.project_id,
            )
        else:
            result = await session.run(
                """
                MATCH (a:GenEntity {id: $a, project: $project}),
                      (b:GenEntity {id: $b, project: $project})
                OPTIONAL MATCH (a)-[e:REL {rel_type: $t}]->(b)
                WITH a, b, e IS NOT NULL AS existed
                MERGE (a)-[r:REL {rel_type: $t}]->(b)
                SET r += $props
                RETURN existed
                """,
                a=a["id"], b=b["id"], t=rel_type, props=props,
                project=ctx.deps.project_id,
            )
        record = await result.single()
        existed = bool(record and record["existed"])

    label = verbe if narrative else rel_type
    # Ré-émission d'une arête déjà en base (#45) : rien de nouveau n'a été écrit
    # → NI carte NI write_log NI check (le MERGE dédupliquait déjà l'arête, mais
    # chaque ré-émission polluait l'UI et le contexte du checker — vu sur les
    # 3 moteurs, doublons intra-tour compris). On garde le tampon de récence :
    # re-mentionner un lien maintient ses extrémités dans le working set.
    if existed:
        await touch_entities(ctx.deps.driver, [a["id"], b["id"]], project=ctx.deps.project_id)
        return f"Relation déjà connue : {a['name']} —[{label}]→ {b['name']} (rien à ajouter)."

    # La carte et le log portent les MOTS de l'auteur pour une arête narrative
    # (thème papier, pas de jargon graphe) ; le type canonique sinon.
    ctx.deps.ui_events.append(
        ToolCard(tool="people", title="Relation ajoutée", subject=a["name"],
                 field=label, added=b["name"],
                 relation=RelationRef(from_id=a["id"], to_id=b["id"], rel_type=rel_type,
                                      verbe_slug=slugify(verbe) if narrative else None))
    )
    extra = f" ({fmt_props(props, skip_reserved=False)})" if props else ""
    ctx.deps.write_log.append(f"relation {a['id']} —[{label}]→ {b['id']}{extra}")
    ctx.deps.touched_ids.add(a["id"])
    ctx.deps.touched_ids.add(b["id"])
    await touch_entities(ctx.deps.driver, [a["id"], b["id"]], project=ctx.deps.project_id)
    # Les deux extrémités d'une nouvelle relation sont candidates au check
    # (relation = là où vivent les contradictions spatiales/relationnelles).
    ctx.deps.check_candidates.add(a["id"])
    ctx.deps.check_candidates.add(b["id"])
    return f"Relation : {a['name']} —[{label}]→ {b['name']}."


async def add_event(
    ctx: RunContext[GenericDeps],
    resume: str,
    participants: list[str] | None = None,
    lieu: str | None = None,
    avant: str | None = None,
) -> str:
    """Enregistre un ÉVÉNEMENT du récit : une action qui SE PASSE à un instant donné
    (ex. « Vance tire sur les consoles », « le réacteur explose »).

    À n'utiliser QUE pour ce qui ARRIVE et fait avancer l'histoire — jamais pour un
    état durable (« est ingénieure », « a un bras mécanique ») qui, lui, est une
    PROPRIÉTÉ du personnage (update_entity). Test : « quand ? » a pour réponse un
    instant → événement ; « quand ? » est absurde (ça tient tout le temps) → ce
    n'est pas un événement.

    L'ordre chronologique et le chaînage NEXT sont gérés AUTOMATIQUEMENT : tu n'as
    pas à numéroter, chaque événement se range à la suite du précédent. Pour un
    événement raconté AVANT un autre (flashback, « trois jours avant X »), passe
    le fragment de résumé de X dans ``avant``.

    Args:
        resume: Ce qui se passe, en une phrase courte (« Silas examine le cadavre »).
        participants: Noms d'entités EXISTANTES qui prennent part à l'événement
            (personnages, objets) — reliées par INVOLVES.
        lieu: Nom du lieu EXISTANT où ça se passe — relié par LOCATED_AT.
        avant: Fragment du résumé d'un événement EXISTANT devant lequel insérer
            cet événement (ordre diégétique). Introuvable ou ambigu → refus.
    """
    text = resume.strip()
    if not text:
        return "Résumé d'événement vide — rien enregistré."

    # ordre auto-incrémenté (en code, pas par le modèle) + id unique : deux actions
    # proches ne doivent PAS fusionner, donc surtout pas de slug du résumé. Le lock
    # sérialise les add_event concurrents d'un même run (sinon collision d'ordre/id).
    proj = ctx.deps.project_id
    async with ctx.deps.event_seq_lock:
        async with ctx.deps.driver.session() as session:
            # Dédup : ne pas recréer un événement au resume identique (le chroniqueur
            # appelle parfois add_event 2x pour la même action dans une seule réponse).
            dup = await session.run(
                "MATCH (e:GenEntity {entity_type: 'evenement', project: $project})"
                " WHERE toLower(e.resume) = toLower($r) RETURN e.id LIMIT 1",
                r=text, project=proj,
            )
            if await dup.single():
                return f"Événement déjà enregistré (ignoré) : {text}."
            # L'ordre (et donc la chaîne NEXT) est PAR PROJET : chaque histoire a sa
            # propre chronologie, les timelines ne s'entrelacent pas (#60).
            result = await session.run(
                "MATCH (e:GenEntity {entity_type: 'evenement', project: $project})"
                " RETURN e.id AS id, e.ordre AS ordre, e.resume AS resume"
                " ORDER BY e.ordre",
                project=proj,
            )
            existing_events = [dict(r) for r in await result.data()]

        # Résolution du fragment `avant` (pure Python, sous le lock)
        ref_event = None
        if avant is not None:
            ref_event, err = resolve_event_fragment(existing_events, avant)
            if err is not None:
                return err

        max_ordre = max((e["ordre"] for e in existing_events), default=0)
        event_id = f"event-{max_ordre + 1}"

        async with ctx.deps.driver.session() as session:
            await session.run(
                "CREATE (e:GenEntity {id: $id, name: $name, entity_type: 'evenement',"
                " resume: $resume, ordre: $ordre, project: $project})",
                id=event_id, name=text, resume=text, ordre=max_ordre + 1, project=proj,
            )

        ordered_ids = [e["id"] for e in existing_events]
        if ref_event is not None:
            # Insertion AVANT la référence : rebuild complet (ordres + chaîne NEXT)
            new_ordered_ids = compute_insert_before(ordered_ids, event_id, ref_event["id"])
            await _rebuild_event_sequence(ctx.deps.driver, proj, new_ordered_ids)
            ordre = new_ordered_ids.index(event_id) + 1
        else:
            # Chemin nominal : chaîne NEXT depuis le dernier event existant
            if existing_events:
                last_id = existing_events[-1]["id"]
                async with ctx.deps.driver.session() as session:
                    await session.run(
                        "MATCH (p:GenEntity {id: $pid, project: $project}),"
                        " (e:GenEntity {id: $id, project: $project})"
                        " MERGE (p)-[:REL {rel_type: 'NEXT'}]->(e)",
                        pid=last_id, id=event_id, project=proj,
                    )
            ordre = max_ordre + 1

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
        node = await find_non_event(ctx.deps.driver, raw, project=proj)
        if not node or node["id"] in seen_ids:
            continue
        seen_ids.add(node["id"])
        async with ctx.deps.driver.session() as session:
            await session.run(
                "MATCH (e:GenEntity {id: $e, project: $project}),"
                " (t:GenEntity {id: $t, project: $project})"
                " MERGE (e)-[r:REL {rel_type: $rel}]->(t)",
                e=event_id, t=node["id"], rel=rel, project=proj,
            )
        linked.append(node["name"])
        ctx.deps.touched_ids.add(node["id"])
        # L'entité IMPLIQUÉE dans un événement est candidate au check (timeline →
        # check temporel « mort puis agit »). Le nœud événement lui-même, non.
        ctx.deps.check_candidates.add(node["id"])

    # Les participants/lieu entrent dans le working set (pas le nœud événement,
    # de toute façon exclu de recent_entities).
    await touch_entities(ctx.deps.driver, seen_ids - {event_id}, project=proj)

    avant_suffix = (
        f" (avant « {ref_event['resume'][:_RESUME_PREVIEW]} »)" if ref_event else ""
    )
    ctx.deps.ui_events.append(
        ToolCard(tool="people", title="Événement", subject=text,
                 field=f"#{ordre}", added=", ".join(linked) or "—", entity_id=event_id)
    )
    ctx.deps.write_log.append(
        f"événement #{ordre} : {text}{avant_suffix} (participants : {', '.join(linked) or '—'})"
    )
    ctx.deps.touched_ids.add(event_id)
    return f"Événement #{ordre} enregistré : {text}{avant_suffix} (participants : {', '.join(linked) or '—'})."


async def move_event(
    ctx: RunContext[GenericDeps],
    resume: str,
    position: str,
    reference: str,
) -> str:
    """Déplace un événement EXISTANT à un autre rang de la chronologie diégétique.

    À utiliser UNIQUEMENT quand l'auteur CORRIGE l'ordre d'un événement déjà noté
    (« en fait c'était avant X », « je raconte dans le désordre »). Ne crée rien.

    La renumérotation et la recousure de la chaîne NEXT sont AUTOMATIQUES.

    Args:
        resume: Fragment du résumé de l'événement à déplacer. Introuvable ou ambigu
            → refus terminal, rien ne change.
        position: 'avant' pour placer AVANT la référence, 'apres' pour APRÈS.
        reference: Fragment du résumé de l'événement de référence. Introuvable ou
            ambigu → refus terminal, rien ne change.
    """
    proj = ctx.deps.project_id
    position_low = position.strip().lower()
    if position_low not in ("avant", "apres", "après"):
        return "Position invalide — utilise 'avant' ou 'apres'."

    async with ctx.deps.event_seq_lock:
        async with ctx.deps.driver.session() as session:
            result = await session.run(
                "MATCH (e:GenEntity {entity_type: 'evenement', project: $project})"
                " RETURN e.id AS id, e.ordre AS ordre, e.resume AS resume"
                " ORDER BY e.ordre",
                project=proj,
            )
            existing_events = [dict(r) for r in await result.data()]

        if not existing_events:
            return "Aucun événement dans la chronologie — rien à déplacer."

        # Résolution stricte — refus terminal si introuvable ou ambigu (#59)
        event_to_move, err = resolve_event_fragment(existing_events, resume)
        if err is not None:
            return err

        ref_event, err = resolve_event_fragment(existing_events, reference)
        if err is not None:
            return err

        assert event_to_move is not None  # garanti par resolve (err est None ici)
        assert ref_event is not None

        if event_to_move["id"] == ref_event["id"]:
            return "L'événement et la référence sont identiques — rien à déplacer."

        ordered_ids = [e["id"] for e in existing_events]
        if position_low == "avant":
            new_ordered_ids = compute_move_before(
                ordered_ids, event_to_move["id"], ref_event["id"]
            )
        else:
            new_ordered_ids = compute_move_after(
                ordered_ids, event_to_move["id"], ref_event["id"]
            )

        await _rebuild_event_sequence(ctx.deps.driver, proj, new_ordered_ids)
        new_ordre = new_ordered_ids.index(event_to_move["id"]) + 1

    # Participants de l'événement déplacé → touched_ids + check_candidates
    # (le juge re-juge ce tour et l'alerte temporelle s'éteint d'elle-même)
    async with ctx.deps.driver.session() as session:
        result = await session.run(
            "MATCH (e:GenEntity {id: $eid, project: $project})"
            "-[:REL {rel_type: 'INVOLVES'}]->(p:GenEntity {project: $project})"
            " RETURN p.id AS pid",
            eid=event_to_move["id"], project=proj,
        )
        participant_ids = [r["pid"] for r in await result.data()]

    for pid in participant_ids:
        ctx.deps.touched_ids.add(pid)
        ctx.deps.check_candidates.add(pid)
    ctx.deps.touched_ids.add(event_to_move["id"])

    pos_label = "avant" if position_low == "avant" else "après"
    ref_resume = ref_event["resume"]
    ref_short = (
        ref_resume[:_RESUME_PREVIEW] + "…"
        if len(ref_resume) > _RESUME_PREVIEW
        else ref_resume
    )
    ctx.deps.ui_events.append(
        ToolCard(
            tool="people",
            title="Événement déplacé",
            subject=event_to_move["resume"],
            field=f"#{new_ordre}",
            added=f"{pos_label} « {ref_short} »",
            entity_id=event_to_move["id"],
        )
    )
    ctx.deps.write_log.append(
        f"événement « {event_to_move['resume'][:_RESUME_PREVIEW]} » déplacé {pos_label} "
        f"« {ref_resume[:_RESUME_PREVIEW]} » → ordre #{new_ordre}"
    )
    return (
        f"Événement « {event_to_move['resume']} » déplacé {pos_label} "
        f"« {ref_resume} » (ordre #{new_ordre})."
    )
