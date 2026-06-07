"""PROTOTYPE noyau générique schemaless — tools + agent + check de cohérence.

Questions mesurées (cf. dataset) :
- Q1 : Mistral Small tient-il la discipline « schéma émergent » (réutiliser
  les types et les noms de propriétés existants, découverts via describe_schema) ?
- Q2 : même code, trois domaines (montage d'abri bois, polar, WW2) ?
- Q3 : le check « voisinage de l'entité + judge LLM » attrape-t-il les
  contradictions (directes et via une relation) sans aucune sémantique codée ?

Modèle de données volontairement minimal :
- nœuds ``:GenEntity`` {id (slug), name, entity_type, ...props libres (str)}
- relations ``:REL`` {rel_type, ...props libres} (type dynamique en propriété,
  Cypher pur sans APOC)

Réutilise AtelierDeps/ToolCard : le prototype resterait branchable sur l'UI atelier.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings

from felix.atelier.deps import AtelierDeps
from felix.atelier.models import ToolCard
from felix.ingest.resolver import slugify
from felix.llm import build_chat_model


@dataclass
class GenericDeps(AtelierDeps):
    # Journal des écritures (ancienne → nouvelle valeur) : le check de
    # cohérence doit voir le DELTA, pas seulement l'état final — une écriture
    # qui écrase une valeur contradictoire rend l'état final auto-cohérent
    # (finding du round 1 : l'alibi de Marco écrasé avant le check).
    write_log: list[str] = field(default_factory=list)


# ─────────────────────────── accès graphe ───────────────────────────

_RESERVED_KEYS = {"id", "name", "entity_type"}


async def _find_node(driver, ref: str) -> dict | None:
    """Entité par slug exact, sinon par nom (contains, insensible à la casse)."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (e:GenEntity)
            WHERE e.id = $slug OR toLower(e.name) CONTAINS toLower($ref)
            RETURN e LIMIT 1
            """,
            slug=slugify(ref),
            ref=ref,
        )
        record = await result.single()
        return dict(record["e"]) if record else None


async def _all_entities(driver) -> list[dict]:
    async with driver.session() as session:
        result = await session.run("MATCH (e:GenEntity) RETURN e ORDER BY e.id")
        return [dict(r["e"]) for r in await result.data()]


async def _all_relations(driver) -> list[dict]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:GenEntity)-[r:REL]->(b:GenEntity)
            RETURN a.id AS from, r.rel_type AS rel_type, properties(r) AS props, b.id AS to
            """
        )
        return [dict(r) for r in await result.data()]


def _fmt_props(props: dict, *, skip_reserved: bool = True) -> str:
    items = [
        f"{k}={v!r}" for k, v in sorted(props.items())
        if not (skip_reserved and k in _RESERVED_KEYS)
    ]
    return ", ".join(items) if items else "(aucune propriété)"


# ─────────────────────────── tools ───────────────────────────


async def describe_schema(ctx: RunContext[GenericDeps]) -> str:
    """Décrit le schéma actuel de la base : types d'entités, noms de propriétés
    et types de relations déjà utilisés.

    À appeler AVANT toute écriture, pour réutiliser les types et noms de
    propriétés existants au lieu d'en inventer de nouveaux.
    """
    entities = await _all_entities(ctx.deps.driver)
    relations = await _all_relations(ctx.deps.driver)
    if not entities:
        return "Base vide : aucun type, aucune propriété. Tu définis le schéma."

    by_type: dict[str, dict] = {}
    for e in entities:
        t = e.get("entity_type", "?")
        slot = by_type.setdefault(t, {"count": 0, "keys": set()})
        slot["count"] += 1
        slot["keys"].update(k for k in e if k not in _RESERVED_KEYS)

    lines = ["Types d'entités existants :"]
    for t, slot in sorted(by_type.items()):
        keys = ", ".join(sorted(slot["keys"])) or "—"
        lines.append(f"- {t} ({slot['count']}) · propriétés : {keys}")

    rel_types = sorted({r["rel_type"] for r in relations})
    lines.append(f"Types de relations : {', '.join(rel_types) if rel_types else '—'}")
    return "\n".join(lines)


async def find_entity(ctx: RunContext[GenericDeps], name: str) -> str:
    """Cherche une entité par nom et retourne ses propriétés et relations.

    Args:
        name: Nom complet ou partiel de l'entité.
    """
    node = await _find_node(ctx.deps.driver, name)
    if not node:
        return f"Aucune entité ne correspond à « {name} »."
    relations = await _all_relations(ctx.deps.driver)
    rel_lines = [
        f"- {r['from']} —[{r['rel_type']}]→ {r['to']}"
        for r in relations
        if node["id"] in (r["from"], r["to"])
    ]
    return (
        f"{node['name']} (id: {node['id']}, type: {node.get('entity_type')})\n"
        f"Propriétés : {_fmt_props(node)}\n"
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
    if await _find_node(ctx.deps.driver, entity_id):
        return f"« {name} » existe déjà (id: {entity_id}) — utilise update_entity."

    clean = {k: v for k, v in (props or {}).items() if k not in _RESERVED_KEYS}
    async with ctx.deps.driver.session() as session:
        await session.run(
            "MERGE (e:GenEntity {id: $id})"
            " ON CREATE SET e.name = $name, e.entity_type = $type"
            " SET e += $props",
            id=entity_id, name=name, type=entity_type, props=clean,
        )
    ctx.deps.ui_events.append(
        ToolCard(title="Entité créée", subject=name, field=entity_type,
                 added=_fmt_props(clean, skip_reserved=False))
    )
    ctx.deps.write_log.append(
        f"création de {entity_id} (type {entity_type}) : {_fmt_props(clean, skip_reserved=False)}"
    )
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
    node = await _find_node(ctx.deps.driver, name)
    if not node:
        return f"« {name} » n'existe pas — utilise add_entity pour la créer."
    clean = {k: v for k, v in props.items() if k not in _RESERVED_KEYS}

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
                 added=_fmt_props(clean, skip_reserved=False))
    )
    suffix = f" — attention, valeurs remplacées : {', '.join(replaced)}" if replaced else ""
    return f"{node['name']} mis à jour : {_fmt_props(clean, skip_reserved=False)}.{suffix}"


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
    a = await _find_node(ctx.deps.driver, from_name)
    b = await _find_node(ctx.deps.driver, to_name)
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
    extra = f" ({_fmt_props(props, skip_reserved=False)})" if props else ""
    ctx.deps.write_log.append(f"relation {a['id']} —[{rel_type}]→ {b['id']}{extra}")
    return f"Relation : {a['name']} —[{rel_type}]→ {b['name']}."


# ─────────────────────────── agent ───────────────────────────

SYSTEM_PROMPT = """\
Tu maintiens une base de connaissances structurée (entités, propriétés,
relations) au fil de la conversation, quel que soit le domaine.

RÈGLES :
1. Avant toute écriture, appelle describe_schema pour connaître les types
   d'entités et les noms de propriétés déjà utilisés dans la base.
2. RÉUTILISE toujours les types et les noms de propriétés existants quand le
   sens correspond. Ne crée JAMAIS deux noms pour le même concept : si
   `date_achat` existe, n'invente pas `achete_en`.
3. Une chose nouvelle → add_entity. Une information sur une chose connue →
   update_entity. Quand deux entités nommées apparaissent dans la même phrase,
   crée chacune ET la relation qui les lie (add_relation).
4. Ne REMPLACE une valeur existante que si l'utilisateur corrige explicitement
   (« correction », « en fait », « plutôt »). Une information qui DIVERGE d'une
   valeur existante (autre source, témoignage…) s'AJOUTE — nouvelle propriété
   ou relation — sans toucher la valeur en place.
5. N'écris RIEN si l'utilisateur te salue, pose une question ou ne donne
   aucun fait nouveau.
6. N'invente aucun fait : tu enregistres ce que l'utilisateur dit, rien de plus.
7. Réponds en français, 2 phrases maximum.
"""


def create_generic_agent() -> Agent[GenericDeps, str]:
    agent = Agent(
        build_chat_model(),
        instructions=SYSTEM_PROMPT,
        deps_type=GenericDeps,
        output_type=str,
        model_settings=ModelSettings(temperature=0.1),
        retries=3,
    )
    agent.tool(describe_schema)
    agent.tool(find_entity)
    agent.tool(add_entity)
    agent.tool(update_entity)
    agent.tool(add_relation)
    return agent


# ──────────────── check de cohérence « voisinage + judge » ────────────────


class CheckVerdict(BaseModel):
    # reason AVANT contradiction : le modèle génère le JSON séquentiellement,
    # le raisonnement doit précéder le verdict (leçon P4 « reason-first »).
    reason: str
    contradiction: bool


CHECK_PROMPT = """\
Tu vérifies la cohérence d'une base de connaissances après une écriture.

ÉTAT ACTUEL (l'entité concernée, ses propriétés, ses relations, les entités liées) :
{context}

ÉCRITURES RÉCENTES (ce qui vient d'être ajouté ou remplacé) :
{writes}

Dans `reason`, raisonne pas à pas en COMMENÇANT par les écritures récentes :
une valeur REMPLACÉE par une valeur incompatible est un conflit à signaler,
pas une simple mise à jour. Compare ensuite les dates entre elles, les
dimensions entre elles, les lieux entre eux.

Puis conclus avec `contradiction` : deux informations ne peuvent-elles
normalement pas être vraies ensemble ? Exemples de contradictions :
- valeurs incompatibles pour une même propriété (avant/après une écriture)
- impossibilité temporelle : agir sur une chose après sa destruction, sa mort ou sa fin
- impossibilité spatiale : un objet plus grand que ce qui le porte ou le contient ;
  être à deux endroits en même temps
- états mutuellement exclusifs

Une information nouvelle, absente ou imprécise n'est PAS une contradiction.
Mais n'invente pas de scénario improbable pour réconcilier deux faits
incompatibles : si la lecture naturelle des faits est incompatible, signale-le.
"""


async def _neighborhood(driver, ref: str) -> str | None:
    """Sous-graphe 1-hop de l'entité : props complètes + relations + voisins complets."""
    node = await _find_node(driver, ref)
    if not node:
        return None
    relations = await _all_relations(driver)
    entities = {e["id"]: e for e in await _all_entities(driver)}

    lines = [f"ENTITÉ : {node['name']} (type: {node.get('entity_type')})",
             f"  propriétés : {_fmt_props(node)}"]
    for r in relations:
        if node["id"] not in (r["from"], r["to"]):
            continue
        other_id = r["to"] if r["from"] == node["id"] else r["from"]
        other = entities.get(other_id, {})
        rel_props = {k: v for k, v in r["props"].items() if k != "rel_type"}
        rel_extra = f" ({_fmt_props(rel_props, skip_reserved=False)})" if rel_props else ""
        lines.append(
            f"RELATION : {r['from']} —[{r['rel_type']}]→ {r['to']}{rel_extra}\n"
            f"  {other.get('name', other_id)} (type: {other.get('entity_type')})"
            f" · propriétés : {_fmt_props(other)}"
        )
    return "\n".join(lines)


async def consistency_check(
    driver, ref: str, write_log: list[str] | None = None
) -> CheckVerdict:
    """Check générique : voisinage de l'entité + journal des écritures, le judge
    cherche une contradiction. Aucune sémantique de domaine."""
    context = await _neighborhood(driver, ref)
    if context is None:
        return CheckVerdict(reason=f"entité « {ref} » introuvable", contradiction=False)
    writes = "\n".join(f"- {w}" for w in write_log) if write_log else "(aucune)"
    judge = Agent(
        build_chat_model(),
        output_type=CheckVerdict,
        model_settings=ModelSettings(temperature=0.0),
        retries=3,
    )
    result = await judge.run(CHECK_PROMPT.format(context=context, writes=writes))
    return result.output
