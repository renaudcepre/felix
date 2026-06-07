"""Modèles du bot atelier — cartes UI poussées par les tools vers le front."""
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
