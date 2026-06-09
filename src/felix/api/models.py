from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    message_history: list[dict[str, object]] = []
    # Bot B uniquement : clé de profil/mode choisie dans l'UI (scenario/chantier/none).
    profile: str = "scenario"


# --- Entités schemaless (:GenEntity / :REL) ---
# Aucune sémantique de domaine : on expose name + entity_type + props libres.
# Les fiches sont génériques côté front, robustes à une structure non garantie.


class EntityRef(BaseModel):
    """Référence minimale vers une entité (extrémité de relation)."""

    id: str
    name: str
    entity_type: str | None = None


class EntitySummary(BaseModel):
    id: str
    name: str
    entity_type: str | None = None
    props: dict[str, Any] = {}


class EntityRelationOut(BaseModel):
    rel_type: str
    direction: str  # "out" (l'entité est source) | "in" (l'entité est cible)
    other: EntityRef


class EntityEventOut(BaseModel):
    ordre: int
    resume: str


class EntityDetail(BaseModel):
    id: str
    name: str
    entity_type: str | None = None
    props: dict[str, Any] = {}
    relations: list[EntityRelationOut] = []
    events: list[EntityEventOut] = []
