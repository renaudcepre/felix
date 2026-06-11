from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from felix.core import DEFAULT_PROJECT


class ChatRequest(BaseModel):
    message: str
    message_history: list[dict[str, object]] = []
    # Bot B uniquement : clé de profil/mode choisie dans l'UI (scenario/chantier/none).
    profile: str = "scenario"
    # Projet/histoire courant (#60) : le front l'envoie à chaque tour (stateless
    # côté serveur). Défaut = projet de repli (anciens clients, curl).
    project: str = DEFAULT_PROJECT


# --- Projets / histoires (#60) ---


class ProjectOut(BaseModel):
    """Un projet du registre (:Project) — le « tenant » d'une histoire."""

    id: str
    name: str
    created_at: int | None = None


class ProjectCreate(BaseModel):
    name: str


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
    # Arête narrative (LIE_A, #68) : le verbe VERBATIM de l'auteur (ce que la
    # fiche affiche) et son slug (complément de clé pour la suppression — la même
    # paire peut porter plusieurs arêtes, une par verbe).
    verbe: str | None = None
    verbe_slug: str | None = None


class EntityEventOut(BaseModel):
    # `id` = clé de suppression d'un événement depuis la fiche (#61).
    id: str
    ordre: int
    resume: str


class EntityPatch(BaseModel):
    """Correction manuelle d'une fiche par l'auteur (#61) — champs tous optionnels,
    on n'applique que ce qui est fourni."""

    name: str | None = None
    props: dict[str, str] = {}
    remove_props: list[str] = []


class EntityDetail(BaseModel):
    id: str
    name: str
    entity_type: str | None = None
    props: dict[str, Any] = {}
    relations: list[EntityRelationOut] = []
    events: list[EntityEventOut] = []
