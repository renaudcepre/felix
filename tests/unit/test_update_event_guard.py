"""Garde anti-événement pour update_entity (issue #58).

Bug : un nœud événement dont le ``name`` contient un nom de personnage est
résolu par ``find_node`` → ``update_entity`` pose des propriétés de personnage
sur l'événement.

Fix : la garde ``check_update_target`` (pur, sans Neo4j) rejette tout nœud
dont ``entity_type='evenement'`` avant toute écriture.

Anti-leakage : les noms de ce module (Brulard, Gretchen, Orvaine) ne doivent
PAS apparaître dans les prompts des agents (src/felix/) — vérification dans
``test_no_test_names_in_prompts``.
"""
from __future__ import annotations

import pathlib
import re

from protest import ProTestSuite

from felix.core.tools import check_update_target

update_event_guard_suite = ProTestSuite("UpdateEventGuard")

# ─────────────────── Noms dédiés à ces tests (univers isolé) ────────────────
# Vérification de non-fuite : voir test_no_test_names_in_prompts ci-dessous.
_TEST_NAMES = ("Brulard", "Gretchen", "Orvaine")

# Nœud événement tel qu'il sort de la base quand la résolution glisse dessus.
_EVENT_NODE = {
    "id": "event-3",
    "name": "Gretchen dit que la pluie efface tout",
    "entity_type": "evenement",
    "ordre": 3,
}

# Nœud personnage ordinaire.
_PERSO_NODE = {
    "id": "brulard",
    "name": "Brulard",
    "entity_type": "personnage",
    "traits": "acariâtre",
}


# ─────────────────────────── Cas REJET (le bug) ──────────────────────────────
@update_event_guard_suite.test()
def test_event_node_is_rejected() -> None:
    """Un nœud événement → message guidant, PAS None (le write ne doit pas avoir lieu)."""
    result = check_update_target(_EVENT_NODE, "Gretchen")
    assert result is not None, "la garde doit rejeter un nœud événement"


@update_event_guard_suite.test()
def test_event_rejection_message_mentions_event() -> None:
    """Le message guidant doit nommer « événement » pour orienter l'agent."""
    result = check_update_target(_EVENT_NODE, "Gretchen")
    assert result is not None
    assert "événement" in result.lower() or "evenement" in result.lower()


@update_event_guard_suite.test()
def test_event_rejection_message_mentions_add_entity() -> None:
    """Le message guidant doit pointer vers add_entity (style cohérent avec add_relation)."""
    result = check_update_target(_EVENT_NODE, "Gretchen")
    assert result is not None
    assert "add_entity" in result


# ─────────────────────────── Cas OK (entité valide) ──────────────────────────
@update_event_guard_suite.test()
def test_non_event_node_passes() -> None:
    """Un nœud personnage ordinaire → None (le write peut avoir lieu)."""
    assert check_update_target(_PERSO_NODE, "Brulard") is None


# ─────────────────────────── Cas introuvable ─────────────────────────────────
@update_event_guard_suite.test()
def test_none_node_returns_message() -> None:
    """Aucun nœud résolu → message « n'existe pas »."""
    result = check_update_target(None, "Orvaine")
    assert result is not None
    assert "Orvaine" in result


@update_event_guard_suite.test()
def test_none_node_message_mentions_add_entity() -> None:
    """Le message d'absence doit guider vers add_entity (cohérence avec l'existant)."""
    result = check_update_target(None, "Orvaine")
    assert result is not None
    assert "add_entity" in result


# ─────────────────────────── Anti-leakage ────────────────────────────────────
@update_event_guard_suite.test()
def test_no_test_names_in_prompts() -> None:
    """Les noms utilisés par ces tests n'entrent JAMAIS dans les prompts des agents.
    Match mot entier : « Brulard » ne doit pas matcher dans un mot plus long."""
    src = pathlib.Path(__file__).parents[3] / "src" / "felix"
    leaked = []
    for py in src.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for name in _TEST_NAMES:
            if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
                leaked.append(f"{name} dans {py.relative_to(src.parent.parent)}")
    assert not leaked, f"noms de test présents dans les sources : {leaked}"
