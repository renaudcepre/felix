"""Persistance du texte SOURCE des pages d'un document (:SourcePage) — méta-nœud
léger, scopé par projet (#60), posé EN CODE à l'ingestion (jamais par le LLM).

Raison d'être : `verify_against_source` (felix.core.check) doit pouvoir relire
la page d'origine d'une fiche pour distinguer une VRAIE incohérence du document
d'une mauvaise LECTURE de Felix — y compris pour une alerte levée bien après
l'ingestion (tour de chat sur une fiche déjà en base), donc le texte des pages
ne peut PAS rester seulement dans la mémoire du run d'ingestion : il doit
survivre en base. `source_pages_for` retrouve ce texte via la relation
DESCRIBED_IN {pages} déjà posée par `felix.core.graph.link_described_in`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from neo4j import AsyncDriver


async def persist_source_pages(
    driver: AsyncDriver,
    document_id: str,
    pages: list[str],
    *,
    project: str,
) -> None:
    """Une :SourcePage par page NON VIDE du document (numérotées à partir de 1,
    même convention que `link_described_in`). MERGE sur {project, document_id,
    page} : idempotent — réingérer le même document met à jour le texte de la
    page, n'en duplique jamais. Les pages vides (déjà nettoyées à rien par
    `clean_pages`) ne produisent aucun nœud — rien à vérifier contre elles."""
    rows = [
        {"page": i, "text": text}
        for i, text in enumerate(pages, start=1)
        if text.strip()
    ]
    if not rows:
        return
    async with driver.session() as session:
        await session.run(
            """
            UNWIND $rows AS row
            MERGE (sp:SourcePage {project: $project, document_id: $doc, page: row.page})
            SET sp.text = row.text
            """,
            rows=rows,
            project=project,
            doc=document_id,
        )


async def source_pages_for(
    driver: AsyncDriver,
    entity_ids: Iterable[str],
    *,
    project: str,
) -> list[tuple[str, int, str]]:
    """Pages sources des entités données : `(titre du document, n° de page,
    texte de la page)`, une entrée par page DESCRIBED_IN (dédupliquée). Une
    entité sans DESCRIBED_IN (fait de chat, jamais rattaché à un document)
    n'apporte simplement aucune page — c'est ce qui fait retomber
    `verify_against_source` sur `unverifiable`, sans cas particulier ici."""
    ids = [i for i in entity_ids if i]
    if not ids:
        return []
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (e:GenEntity {project: $project})
                  -[r:REL {rel_type: 'DESCRIBED_IN'}]->(d:GenEntity {project: $project})
            WHERE e.id IN $ids
            UNWIND coalesce(r.pages, []) AS page
            MATCH (sp:SourcePage {project: $project, document_id: d.id, page: page})
            RETURN DISTINCT d.name AS title, page AS page, sp.text AS text
            ORDER BY d.name, page
            """,
            ids=ids,
            project=project,
        )
        return [(r["title"], r["page"], r["text"]) for r in await result.data()]
