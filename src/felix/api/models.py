from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from felix.core import DEFAULT_PROJECT


class ChatRequest(BaseModel):
    message: str
    # Historique threadé du maître, sérialisé par le front au tour précédent
    # (format ModelMessagesTypeAdapter). PRIORITAIRE si fourni : ce chemin sert
    # aux evals et aux e2e qui injectent un historique contrôlé. Si vide, la
    # route charge le fil serveur depuis :Thread (load_llm_history) — c'est le
    # chemin normal du front web, qui ne gère plus d'état localStorage (#63).
    message_history: list[dict[str, object]] = []
    # Bot B uniquement : clé de profil/mode choisie dans l'UI (emergent/scenario/
    # chantier/maintenance/none). Défaut = emergent (cf. DEFAULT_PROFILE).
    profile: str = "emergent"
    # Projet/histoire courant (#60) : le front l'envoie à chaque tour (stateless
    # côté serveur). Défaut = projet de repli (anciens clients, curl).
    project: str = DEFAULT_PROJECT


# --- Conversation en graphe (#63) ---


class ConversationMessageOut(BaseModel):
    """Un message de la conversation active, exposé par GET /api/atelier/conversation.

    `payload` est décodé en dict côté API (la base stocke une string JSON) —
    None pour kind='text', objet pour kind='tool'/'alert'/'report' (#import,
    carte de résumé d'ingestion — cf. felix.ingest.document.IngestReport)."""

    id: str
    role: str  # 'user' | 'felix'
    kind: str  # 'text' | 'tool' | 'alert' | 'report'
    body: str
    ord: int
    payload: dict[str, Any] | None = None


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


class EntitySource(BaseModel):
    """Premier document DESCRIBED_IN d'une entité — titre + pages où elle
    apparaît (#73, carte de la liste : « <titre>, p. N »)."""

    title: str
    pages: list[int] = []


class EntitySummary(BaseModel):
    """Résumé d'une entité pour la liste (#73) : pas de `props` libres — la
    carte affiche des compteurs, pas une prop arbitraire. La fiche complète
    (`EntityDetail`) reste l'endroit où lire les propriétés."""

    id: str
    name: str
    entity_type: str | None = None
    prop_count: int = 0
    relation_count: int = 0
    source: EntitySource | None = None


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
