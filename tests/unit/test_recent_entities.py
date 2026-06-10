"""Working set d'entités récentes — garanties STRUCTURELLES contre les doublons d'identité.

Le bug « baptême différé » (session Adator) : la fiche « Mage Noir » existe, l'auteur
dit « le mage noir se nomme Alikazeth » → la passe 1 crée une fiche neuve au lieu de
renommer, car rien ne lui montre la base avant d'écrire (elle n'appelle pas find_entity
spontanément, et l'historique threadé du maître ne contient plus ses écritures passées).

Fix neuro-symbolique : la route injecte EN CODE un bloc borné « entités déjà en base »
(les N plus récemment touchées, pas toute la base) en tête du prompt des extracteurs.
Ici on teste la partie PURE : le rendu du bloc, et la borne configurée.
"""
from __future__ import annotations

from protest import ProTestSuite

from felix.config import Settings
from felix.core.graph import render_recent_block

recent_entities_suite = ProTestSuite("RecentEntities")


@recent_entities_suite.test()
def test_empty_rows_render_nothing() -> None:
    """Base vide (ou aucune entité touchée) → pas de bloc, le prompt reste nu."""
    assert render_recent_block([]) == ""


@recent_entities_suite.test()
def test_renders_names_and_types_in_order() -> None:
    """Le bloc liste nom [type] dans l'ordre reçu (récence d'abord — l'ordre EST l'info)."""
    rows = [
        {"name": "Mage Noir", "entity_type": "personnage"},
        {"name": "Adator", "entity_type": "lieu"},
    ]
    block = render_recent_block(rows)
    assert "Mage Noir [personnage]" in block
    assert "Adator [lieu]" in block
    assert block.index("Mage Noir") < block.index("Adator")


@recent_entities_suite.test()
def test_block_carries_rename_instruction() -> None:
    """Le bloc rappelle la consigne anti-doublon : nommer une fiche suivie = rename_entity."""
    block = render_recent_block([{"name": "Mage Noir", "entity_type": "personnage"}])
    assert "rename_entity" in block


@recent_entities_suite.test()
def test_block_is_marked_as_context_not_content() -> None:
    """Le bloc se distingue du message de l'auteur (l'extracteur ne doit pas
    l'extraire comme du contenu nouveau)."""
    block = render_recent_block([{"name": "Adator", "entity_type": "lieu"}])
    assert block.startswith("[")  # préambule balisé, pas de la prose d'auteur


@recent_entities_suite.test()
def test_limit_is_configurable_with_sane_default() -> None:
    """La borne vit dans la config (FLX_RECENT_ENTITIES_LIMIT) — à 400 entités on
    n'injecte JAMAIS toute la base."""
    assert Settings.model_fields["recent_entities_limit"].default == 30
