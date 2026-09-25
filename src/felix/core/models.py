"""Modèles du noyau générique — cartes UI poussées par les tools vers le front.

Déplacé depuis felix.atelier.models : la carte est désormais celle du noyau, le
bot B (atelier) la ré-exporte pour compatibilité.
"""

from __future__ import annotations

from pydantic import BaseModel


class RelationRef(BaseModel):
    """Référence complète d'une relation orientée — la clé de sa suppression.

    `verbe_slug` complète la clé pour une arête narrative (LIE_A) : plusieurs
    arêtes peuvent lier la même paire, une par verbe (#68)."""

    from_id: str
    to_id: str
    rel_type: str
    verbe_slug: str | None = None


class PropChange(BaseModel):
    """Un champ MODIFIÉ (pas ajouté) par update_entity — avant/après (#72).

    Émis UNIQUEMENT quand la valeur existait déjà et diffère de la nouvelle
    (cf. `plan_property_update`/`update_entity`) : jamais pour un ajout,
    jamais quand la valeur est inchangée."""

    field: str
    before: str
    after: str


class ToolCard(BaseModel):
    """Carte « tool » du fil atelier — alignée sur AtelierMsg côté front."""

    kind: str = "tool"
    tool: str = "fiche"  # icône côté front : 'fiche' | 'people'
    title: str
    subject: str
    field: str
    added: str
    # Champs MODIFIÉS (valeur remplacée), distincts de `added` — le front
    # affiche « champ : avant → après » pour ceux-ci au lieu de « + ajouté »
    # (#72). None/vide : cette carte n'a rien modifié, que des ajouts.
    changes: list[PropChange] | None = None
    # Cible de la carte, pour les actions ✎/🗑 du front (#61). `entity_id` pour
    # une fiche (ou un événement), `relation` pour une arête. None : pas d'action
    # possible sur cette carte (ex. fusion — la source n'existe plus).
    entity_id: str | None = None
    relation: RelationRef | None = None
