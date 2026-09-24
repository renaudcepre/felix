"""Moteur de migration du passé — la brique « appliquer un changement de schéma
validé aux entités/relations déjà en base ».

Le profil évolue au fil des documents ingérés (détecteur — hors scope ici) ;
l'humain valide chaque proposition (UI — hors scope) ; ce module applique le
changement VALIDÉ au graphe existant, pour que l'ancien récit se relise sous le
nouveau schéma. Pas de détection, pas de persistance de profil, pas d'appel LLM
ici : un seul concept, ``SchemaChange`` (union discriminée), et une seule
fonction d'application qui calcule un PLAN puis l'écrit (ou pas, en preview).

Deux cas concrets, pas un par fonction :
- ``PromoteVerbs`` : des paraphrases narratives (LIE_A + verbe) deviennent un
  type structurel du domaine (ex. « règle »/« pilote » → CONTROLS) ;
- ``MergeTypes`` : un ou plusieurs entity_type se fondent dans un seul (un
  renommage est une fusion à une seule source).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field

from felix.core.graph import NARRATIVE_REL, REL_RESERVED_KEYS

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# Relations posées PAR LE CODE (chronologie, ingestion) : jamais la cible d'une
# promotion de verbe — ce ne sont pas des relations de DOMAINE.
_MACHINERY_RELATION_TYPES = frozenset({"DESCRIBED_IN", "INVOLVES", "NEXT"})

# Types d'entité machinerie (chronologie, ingestion) : jamais la cible d'une
# fusion venant d'un AUTRE type — sinon des entités de domaine deviennent des
# noeuds événement/document hors de leur mécanique dédiée.
_MACHINERY_ENTITY_TYPES = frozenset({"evenement", "document"})

_UPPER_SNAKE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class PromoteVerbs(BaseModel):
    """Promeut des paraphrases narratives (LIE_A + verbe) vers un type structurel.

    Chaque arête LIE_A dont ``verbe_slug`` est dans ``verbe_slugs`` devient une
    arête typée ``rel_type`` — sens INVERSÉ si ``reverse`` (verbe passif, ex.
    « est réglé par »). La traçabilité survit dans ``verbe_origine`` (liste des
    verbes verbatim d'origine) posé sur l'arête typée ; ``verbe``/``verbe_slug``
    disparaissent (ce ne sont plus des propriétés du type narratif).
    """

    kind: Literal["promote_verbs"] = "promote_verbs"
    verbe_slugs: list[str]
    rel_type: str
    reverse: bool = False


class MergeTypes(BaseModel):
    """Fusionne un ou plusieurs entity_type dans UN type cible.

    Un renommage de type est une fusion à une seule source (``sources=[x]``).
    """

    kind: Literal["merge_types"] = "merge_types"
    sources: list[str]
    target: str


# Union discriminée : UN concept (« un changement de schéma »), deux formes.
SchemaChange = Annotated[PromoteVerbs | MergeTypes, Field(discriminator="kind")]


class ChangeReport(BaseModel):
    """Rapport d'un changement de schéma — identique en preview et en réel.

    ``observed_pairs`` (subject entity_type, object entity_type) sert plus
    tard à amorcer le domaine/portée de la relation dans le profil. ``samples``
    porte jusqu'à 5 lignes lisibles par un humain (la file de validation les
    montre avant le clic). ``verbes`` (PromoteVerbs seulement) liste les verbes
    VERBATIM d'origine, dédupliqués en ordre stable — c'est le matériau que
    ``core.profile_evolution.evolve_profile`` utilise pour construire le
    ``RelationSpec`` (gloss, examples) du type promu."""

    change: PromoteVerbs | MergeTypes
    edges_converted: int = 0
    edges_collapsed: int = 0
    entities_retyped: int = 0
    observed_pairs: list[tuple[str, str]] = Field(default_factory=list)
    samples: list[str] = Field(default_factory=list)
    verbes: list[str] = Field(default_factory=list)


def _validate_change(change: PromoteVerbs | MergeTypes) -> None:
    """Gardes de refus, AVANT tout calcul — ValueError avec message FR clair.

    Refus volontairement stricts (pas de contournement silencieux) : une
    promotion vers la machinerie casserait la mécanique dédiée (chronologie,
    ingestion) qui suppose ce type SEUL responsable de ces arêtes/entités.
    """
    if isinstance(change, PromoteVerbs):
        rel_type = change.rel_type
        if rel_type == NARRATIVE_REL:
            raise ValueError(
                f"Impossible de promouvoir vers « {NARRATIVE_REL} » : c'est le "
                "type narratif lui-même, pas un type structurel cible."
            )
        if not rel_type or not _UPPER_SNAKE_RE.match(rel_type):
            raise ValueError(
                f"« {rel_type} » n'est pas un type de relation valide — il faut "
                "du UPPER_SNAKE_CASE non vide (ex. CONTROLS)."
            )
        if rel_type in _MACHINERY_RELATION_TYPES:
            raise ValueError(
                f"« {rel_type} » est une relation posée par le code (chronologie "
                "ou ingestion) — on ne peut pas y promouvoir des verbes narratifs."
            )
    else:
        target = change.target
        if target in _MACHINERY_ENTITY_TYPES and any(s != target for s in change.sources):
            raise ValueError(
                f"« {target} » est un type machinerie (chronologie ou ingestion) "
                "— on ne peut pas y fusionner d'autres types."
            )


async def _fetch_matching_narrative_edges(
    driver: AsyncDriver, verbe_slugs: list[str], *, project: str
) -> list[dict]:
    """Arêtes LIE_A du projet dont le verbe_slug est promu — triées pour un
    plan déterministe (groupage et échantillons stables d'un run à l'autre)."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:GenEntity {project: $project})
                  -[r:REL {rel_type: $narr}]->
                  (b:GenEntity {project: $project})
            WHERE r.verbe_slug IN $slugs
            RETURN a.id AS from_id, a.entity_type AS from_type, a.name AS from_name,
                   b.id AS to_id, b.entity_type AS to_type, b.name AS to_name,
                   r.verbe AS verbe, r.verbe_slug AS verbe_slug, properties(r) AS props
            ORDER BY a.id, b.id, r.verbe_slug
            """,
            project=project, narr=NARRATIVE_REL, slugs=verbe_slugs,
        )
        return [dict(r) for r in await result.data()]


async def _fetch_existing_typed_edge(
    driver: AsyncDriver, from_id: str, to_id: str, rel_type: str, *, project: str
) -> dict | None:
    """Propriétés de l'arête typée (pair, rel_type) déjà en base, s'il y en a une
    — c'est la cible de collapse quand une promotion retombe sur un lien déjà
    posé par le code ou un run précédent."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:GenEntity {id: $from_id, project: $project})
                  -[r:REL {rel_type: $rel_type}]->
                  (b:GenEntity {id: $to_id, project: $project})
            RETURN properties(r) AS props
            """,
            from_id=from_id, to_id=to_id, rel_type=rel_type, project=project,
        )
        record = await result.single()
        return dict(record["props"]) if record else None


async def _write_typed_edge(  # noqa: PLR0913 — l'arête finale a une clé composite + sa charge
    driver: AsyncDriver, from_id: str, to_id: str, rel_type: str,
    verbe_origine: list[str], extra_props: dict, *, project: str,
) -> None:
    """MERGE de l'arête typée finale — clé (pair, rel_type), comme add_relation
    pour toute relation non-narrative (cf. felix.core.tools.add_relation)."""
    async with driver.session() as session:
        await session.run(
            """
            MATCH (a:GenEntity {id: $from_id, project: $project}),
                  (b:GenEntity {id: $to_id, project: $project})
            MERGE (a)-[t:REL {rel_type: $rel_type}]->(b)
            SET t.verbe_origine = $verbe_origine, t += $extra_props
            """,
            from_id=from_id, to_id=to_id, rel_type=rel_type,
            verbe_origine=verbe_origine, extra_props=extra_props, project=project,
        )


async def _delete_narrative_edge(
    driver: AsyncDriver, from_id: str, to_id: str, verbe_slug: str, *, project: str
) -> None:
    """Supprime UNE arête LIE_A d'origine (clé pair + verbe_slug — plusieurs
    paraphrases peuvent lier la même paire, cf. graph.py)."""
    async with driver.session() as session:
        await session.run(
            """
            MATCH (a:GenEntity {id: $from_id, project: $project})
                  -[r:REL {rel_type: $narr, verbe_slug: $vs}]->
                  (b:GenEntity {id: $to_id, project: $project})
            DELETE r
            """,
            from_id=from_id, to_id=to_id, narr=NARRATIVE_REL, vs=verbe_slug,
            project=project,
        )


def _dedupe_verbes(rows: list[dict]) -> list[str]:
    """Verbes VERBATIM d'origine, dédupliqués en ordre stable — matériau de
    l'évolution du profil (gloss/examples du RelationSpec, cf. profile_evolution)."""
    verbes: list[str] = []
    for row in rows:
        if row["verbe"] not in verbes:
            verbes.append(row["verbe"])
    return verbes


async def _apply_promote_verbs(
    driver: AsyncDriver, change: PromoteVerbs, *, project: str, preview: bool
) -> ChangeReport:
    rows = await _fetch_matching_narrative_edges(driver, change.verbe_slugs, project=project)
    verbes = _dedupe_verbes(rows)

    # Groupage par paire FINALE (après inversion éventuelle) : deux paraphrases
    # sur la même paire — ou une paraphrase qui retombe sur l'autre sens d'une
    # paire déjà inversée — doivent fusionner en UNE arête typée.
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        key = (row["to_id"], row["from_id"]) if change.reverse else (row["from_id"], row["to_id"])
        groups.setdefault(key, []).append(row)

    edges_collapsed = 0
    observed_pairs: set[tuple[str, str]] = set()
    samples: list[str] = []

    for (new_from, new_to), group_rows in groups.items():
        existing = await _fetch_existing_typed_edge(
            driver, new_from, new_to, change.rel_type, project=project
        )
        collapsed = len(group_rows) > 1 or existing is not None
        if collapsed:
            edges_collapsed += 1

        # verbe_origine : l'existant d'abord (il gagne sur conflit de props),
        # puis les verbes NOUVEAUX de ce groupe, dédupliqués en ordre stable.
        verbe_origine: list[str] = list(existing.get("verbe_origine") or []) if existing else []
        for row in group_rows:
            if row["verbe"] not in verbe_origine:
                verbe_origine.append(row["verbe"])

        # Props libres : existant gagne sur conflit (« existing values win »),
        # complétées par celles des LIE_A d'origine (rel_type/verbe/verbe_slug
        # exclus — ce ne sont plus des props de l'arête typée).
        extra_props: dict = {
            k: v for k, v in (existing or {}).items()
            if k not in REL_RESERVED_KEYS and k != "verbe_origine"
        }
        for row in group_rows:
            for key, value in row["props"].items():
                if key in REL_RESERVED_KEYS:
                    continue
                extra_props.setdefault(key, value)

        first = group_rows[0]
        from_type = first["to_type"] if change.reverse else first["from_type"]
        to_type = first["from_type"] if change.reverse else first["to_type"]
        observed_pairs.add((from_type, to_type))

        new_from_name = first["to_name"] if change.reverse else first["from_name"]
        new_to_name = first["from_name"] if change.reverse else first["to_name"]
        for row in group_rows:
            if len(samples) >= 5:  # noqa: PLR2004 — plafond du contrat (max 5 échantillons)
                break
            before = f"{row['from_name']} —[{row['verbe']}]→ {row['to_name']}"
            after = f"{new_from_name} —[{change.rel_type}]→ {new_to_name}"
            samples.append(f"« {before} » → « {after} »")

        if not preview:
            await _write_typed_edge(
                driver, new_from, new_to, change.rel_type,
                verbe_origine, extra_props, project=project,
            )
            for row in group_rows:
                await _delete_narrative_edge(
                    driver, row["from_id"], row["to_id"], row["verbe_slug"],
                    project=project,
                )

    return ChangeReport(
        change=change,
        edges_converted=len(rows),
        edges_collapsed=edges_collapsed,
        observed_pairs=sorted(observed_pairs),
        samples=samples,
        verbes=verbes,
    )


async def _apply_merge_types(
    driver: AsyncDriver, change: MergeTypes, *, project: str, preview: bool
) -> ChangeReport:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (e:GenEntity {project: $project})
            WHERE e.entity_type IN $sources
            RETURN e.id AS id, e.name AS name, e.entity_type AS entity_type
            ORDER BY e.id
            """,
            project=project, sources=change.sources,
        )
        rows = [dict(r) for r in await result.data()]

    samples = [
        f"{row['name']} [{row['entity_type']}] → [{change.target}]" for row in rows[:5]
    ]

    if not preview and rows:
        async with driver.session() as session:
            await session.run(
                """
                MATCH (e:GenEntity {project: $project})
                WHERE e.entity_type IN $sources
                SET e.entity_type = $target
                """,
                project=project, sources=change.sources, target=change.target,
            )

    return ChangeReport(
        change=change,
        entities_retyped=len(rows),
        samples=samples,
    )


async def apply_schema_change(
    driver: AsyncDriver, change: PromoteVerbs | MergeTypes, *, project: str,
    preview: bool = False,
) -> ChangeReport:
    """Applique (ou prévisualise) un changement de schéma VALIDÉ au graphe existant.

    Un seul chemin de calcul pour les deux modes : le plan (arêtes/entités
    concernées, échantillons, comptes) est calculé de façon identique ;
    ``preview=True`` rend le même rapport SANS écrire — la file de validation
    montre exactement ce qui sera fait avant que l'humain ne clique.

    Args:
        driver: driver Neo4j.
        change: le changement validé (PromoteVerbs ou MergeTypes).
        project: histoire/projet scopé — jamais de fuite inter-projet.
        preview: si vrai, calcule le rapport sans écrire.
    """
    _validate_change(change)
    if isinstance(change, PromoteVerbs):
        return await _apply_promote_verbs(driver, change, project=project, preview=preview)
    return await _apply_merge_types(driver, change, project=project, preview=preview)
