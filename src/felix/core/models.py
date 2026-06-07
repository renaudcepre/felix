"""Modèles du noyau générique — cartes UI poussées par les tools vers le front.

Déplacé depuis felix.atelier.models : la carte est désormais celle du noyau, le
bot B (atelier) la ré-exporte pour compatibilité.
"""
from __future__ import annotations

from pydantic import BaseModel


class ToolCard(BaseModel):
    """Carte « tool » du fil atelier — alignée sur AtelierMsg côté front."""

    kind: str = "tool"
    tool: str = "fiche"  # icône côté front : 'fiche' | 'people'
    title: str
    subject: str
    field: str
    added: str
