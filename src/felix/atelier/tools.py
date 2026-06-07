"""Tools du copilote atelier — lecture + écriture du world model.

Parti pris MVP : tout en français (prompt + descriptions de tools), cohérent
avec le produit et le modèle Mistral — l'inverse du bot A (full EN, leçon des
petits modèles 7B). Les evals trancheront si ce choix tient.
"""
from __future__ import annotations

from pydantic_ai import RunContext

from felix.atelier.deps import AtelierDeps
from felix.atelier.models import ToolCard
from felix.graph import repositories as repo
from felix.ingest.resolver import slugify


async def list_characters(ctx: RunContext[AtelierDeps]) -> str:
    """Liste tous les personnages déjà présents dans la bible (nom + id).

    À appeler avant toute création pour vérifier qu'un personnage n'existe pas déjà.
    """
    chars = await repo.list_all_characters(ctx.deps.driver)
    if not chars:
        return "La bible ne contient encore aucun personnage."
    lines = [f"- {c['name']} (id: {c['id']})" for c in chars]
    return "Personnages de la bible :\n" + "\n".join(lines)


async def add_character(
    ctx: RunContext[AtelierDeps], name: str, background: str | None = None
) -> str:
    """Crée la fiche d'un nouveau personnage dans la bible.

    À appeler uniquement quand l'auteur décrit un personnage qui n'existe pas encore.

    Args:
        name: Nom du personnage tel que l'auteur le donne (ex: 'Jean', 'Marie Lavalle').
        background: Ce que l'auteur vient de dire sur ce personnage, repris en une ou
            deux phrases factuelles, sans rien inventer. Omettre si l'auteur n'a donné
            que le nom.
    """
    char_id = slugify(name)
    if not char_id:
        return f"Nom invalide : « {name} »."

    created = await repo.create_character(ctx.deps.driver, char_id, name, background)
    if not created:
        return f"« {name} » existe déjà dans la bible (id: {char_id}) — fiche inchangée."

    ctx.deps.ui_events.append(
        ToolCard(
            title="Fiche créée",
            subject=name,
            field="Background",
            added=background or "Nouveau personnage — fiche à compléter.",
        )
    )
    return f"Fiche créée pour {name} (id: {char_id})."
