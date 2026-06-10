"""Human-in-the-loop (#61) — l'auteur corrige/supprime depuis l'UI, le LLM le SAIT.

Le besoin : quand le LLM se trompe (perso inventé, relation hallucinée), la seule
correction possible était de RACONTER la correction en espérant que l'extraction
la comprenne. Désormais chaque action manuelle (DELETE/PATCH API) laisse un
tombstone `:UserEdit` en base, et la route injecte EN CODE un bloc « décisions de
l'auteur » aux extracteurs (+ au maître, une fois) — sinon l'entité supprimée
revit au tour suivant via l'historique threadé.

Ici on teste les parties PURES : le rendu du bloc, le contrat des cartes (id de
la cible embarqué — sans lui, aucun bouton 🗑 possible), et les bornes config.
"""
from __future__ import annotations

from protest import ProTestSuite

from felix.api.models import EntityEventOut
from felix.config import Settings
from felix.core.models import ToolCard
from felix.core.user_edits import render_user_edits_block

user_edits_suite = ProTestSuite("UserEdits")


@user_edits_suite.test()
def test_empty_edits_render_nothing() -> None:
    """Aucune action manuelle → pas de bloc, le prompt reste nu (cas nominal)."""
    assert render_user_edits_block([]) == ""


@user_edits_suite.test()
def test_renders_details_in_order() -> None:
    """Le bloc liste les actions (détail) dans l'ordre reçu."""
    rows = [
        {"kind": "suppression", "detail": "l'entité « Maximilien » (personnage) a été supprimée"},
        {"kind": "correction", "detail": "« Vels » renommée « Velsgarde »"},
    ]
    block = render_user_edits_block(rows)
    assert "Maximilien" in block
    assert "Velsgarde" in block
    assert block.index("Maximilien") < block.index("Velsgarde")


@user_edits_suite.test()
def test_block_is_marked_as_context_not_content() -> None:
    """Balisé comme contexte : l'extracteur ne doit pas l'extraire comme du récit."""
    block = render_user_edits_block([{"kind": "suppression", "detail": "x supprimée"}])
    assert block.startswith("[")


@user_edits_suite.test()
def test_block_says_author_decision_and_no_recreate() -> None:
    """Le bloc porte les DEUX consignes : c'est l'AUTEUR qui a décidé (pas un état
    de base quelconque), et on ne recrée pas ce qui a été supprimé."""
    block = render_user_edits_block([{"kind": "suppression", "detail": "x supprimée"}])
    assert "auteur" in block.lower()
    assert "ne recrée" in block.lower()


@user_edits_suite.test()
def test_limits_are_configurable_with_sane_defaults() -> None:
    """Borne (nb d'actions injectées) et TTL (purge) vivent dans la config."""
    assert Settings.model_fields["user_edits_limit"].default == 12
    assert Settings.model_fields["user_edits_ttl_minutes"].default == 240


@user_edits_suite.test()
def test_tool_card_carries_target_entity_id() -> None:
    """La carte du chat porte l'ID de sa cible — sans lui, pas de ✎/🗑 possible.
    Optionnel (None) : certaines cartes n'ont pas de cible unique (fusion…)."""
    fields = ToolCard.model_fields
    assert "entity_id" in fields
    assert fields["entity_id"].default is None


@user_edits_suite.test()
def test_tool_card_carries_relation_ref() -> None:
    """Une carte « Relation ajoutée » porte la référence complète (from, to, type) :
    c'est la clé de suppression d'une relation orientée."""
    card = ToolCard(
        title="Relation ajoutée", subject="Nora", field="KNOWS", added="Castan",
        relation={"from_id": "nora", "to_id": "castan", "rel_type": "KNOWS"},
    )
    assert card.relation is not None
    assert card.relation.from_id == "nora"
    assert card.relation.rel_type == "KNOWS"


@user_edits_suite.test()
def test_entity_event_out_carries_id() -> None:
    """La chronologie de la fiche expose l'id de chaque événement : c'est la clé
    de suppression d'un événement depuis la fiche."""
    assert "id" in EntityEventOut.model_fields
