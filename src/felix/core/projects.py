"""Registre des projets/histoires (#60) — le « tenant » du graphe schemaless.

Deux histoires jouées dans la même base ne doivent jamais se voir : chaque
:GenEntity (et chaque tombstone :UserEdit) porte une prop `project`, posée EN
CODE par les writers (jamais par le LLM, même mécanique que `last_touched`), et
filtrée par TOUS les lecteurs. Le nœud `:Project` ne porte que les métadonnées
(registre) — il servira d'ancre aux :Message de la conversation en graphe (#63)
et à l'export par histoire (#42).

Neo4j Community : pas de multi-database ni de contrainte composite — l'unicité
de {id, project} est garantie par les clés de MERGE des writers, pas par une
contrainte (suffisant en local-first mono-utilisateur).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from felix.ingest.resolver import slugify

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# Projet de repli : migration de l'existant, evals, appels sans sélection.
DEFAULT_PROJECT = "defaut"


async def list_projects(driver: AsyncDriver) -> list[dict]:
    """Tous les projets du registre, plus récents d'abord (le défaut en dernier
    s'il est seul — l'ordre de création est l'ordre naturel du sélecteur)."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (p:Project)
            RETURN p.id AS id, p.name AS name, p.created_at AS created_at
            ORDER BY p.created_at DESC
            """
        )
        return [dict(r) for r in await result.data()]


async def create_project(driver: AsyncDriver, name: str) -> dict | None:
    """Crée (ou retrouve) un projet par nom. Rend None sur nom vide/invalide.

    MERGE sur l'id (slug du nom) : recréer « Alger 1957 » ne duplique pas le
    registre — on retombe sur l'histoire existante, c'est le comportement voulu
    (le sélecteur ne propose jamais deux fois la même histoire)."""
    project_id = slugify(name)
    if not project_id:
        return None
    async with driver.session() as session:
        result = await session.run(
            """
            MERGE (p:Project {id: $id})
            ON CREATE SET p.name = $name, p.created_at = timestamp()
            RETURN p.id AS id, p.name AS name, p.created_at AS created_at
            """,
            id=project_id, name=name.strip(),
        )
        record = await result.single()
        return dict(record) if record else None


async def ensure_project_scoping(driver: AsyncDriver) -> None:
    """Migration idempotente au démarrage : le monde d'avant #60 devient le
    projet par défaut. Toute :GenEntity (ou :UserEdit) sans `project` est
    adoptée par `defaut` — les bases déjà scopées ne bougent pas."""
    async with driver.session() as session:
        await session.run(
            "MERGE (p:Project {id: $id}) "
            "ON CREATE SET p.name = $name, p.created_at = timestamp()",
            id=DEFAULT_PROJECT, name="Histoire par défaut",
        )
        await session.run(
            "MATCH (e:GenEntity) WHERE e.project IS NULL SET e.project = $p",
            p=DEFAULT_PROJECT,
        )
        await session.run(
            "MATCH (u:UserEdit) WHERE u.project IS NULL SET u.project = $p",
            p=DEFAULT_PROJECT,
        )
