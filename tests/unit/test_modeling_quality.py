"""Qualité de modélisation — garanties STRUCTURELLES contre le churn de propriétés.

Test déterministe (sans LLM) des deux décisions actées :
1. La trajectoire d'un personnage vit dans la CHRONOLOGIE → pas de prop `arc` dans
   les clés suggérées (sinon la passe entités y déverse l'action du beat, qui écrase
   la précédente — churn observé sur « Alger 1957 »).
2. Le relieur (passe 2) ne peut PLUS modifier de propriétés : son jeu d'outils exclut
   `update_entity` (il garde `add_entity` en backfill). Supprime la 2e source de churn
   (re-update des mêmes props par-dessus la passe 1).
"""
from __future__ import annotations

from protest import ProTestSuite

from felix.atelier.agent import RELATION_TOOLS
from felix.core.profile import SCENARIO_PROFILE
from felix.core.tools import plan_property_update

modeling_quality_suite = ProTestSuite("ModelingQuality")


@modeling_quality_suite.test()
def test_personnage_has_no_arc_key() -> None:
    """L'arc se lit dans les événements, pas dans une propriété écrasable."""
    perso = next(et for et in SCENARIO_PROFILE.entity_types if et.name == "personnage")
    assert "arc" not in perso.keys


@modeling_quality_suite.test()
def test_personnage_keeps_durable_keys() -> None:
    """On garde les vraies propriétés DURABLES (ce qu'un personnage EST)."""
    perso = next(et for et in SCENARIO_PROFILE.entity_types if et.name == "personnage")
    assert {"background", "age", "traits"} <= set(perso.keys)


@modeling_quality_suite.test()
def test_relieur_cannot_update_properties() -> None:
    """Le relieur n'a pas update_entity → il ne peut plus churner les props."""
    names = {t.__name__ for t in RELATION_TOOLS}
    assert "update_entity" not in names


@modeling_quality_suite.test()
def test_relieur_keeps_relation_and_backfill_tools() -> None:
    """Mais il garde add_relation (sa tâche) et add_entity (backfill d'une entité ratée)."""
    names = {t.__name__ for t in RELATION_TOOLS}
    assert "add_relation" in names
    assert "add_entity" in names


# ─────── Garde anti-écrasement : update_entity n'écrase pas une valeur existante ───────
@modeling_quality_suite.test()
def test_overwrite_blocked_without_correction() -> None:
    """Écraser un `traits` durable par une action (sans correction) → bloqué, durable préservé."""
    existing = {"traits": "cheveux gris, regard las"}
    to_set, blocked = plan_property_update(
        existing, {"traits": "sourit amèrement"}, is_correction=False
    )
    assert blocked == ["traits"]
    assert "traits" not in to_set


@modeling_quality_suite.test()
def test_overwrite_allowed_with_correction() -> None:
    """Mais une correction EXPLICITE de l'auteur passe (l'agent signale is_correction)."""
    existing = {"age": "40 ans"}
    to_set, blocked = plan_property_update(
        existing, {"age": "45 ans"}, is_correction=True
    )
    assert blocked == []
    assert to_set == {"age": "45 ans"}


@modeling_quality_suite.test()
def test_new_key_always_applied() -> None:
    """Une nouvelle clé (fait durable inédit) passe toujours — c'est l'enrichissement additif."""
    to_set, blocked = plan_property_update(
        {"traits": "colonial"}, {"background": "fils de légionnaire"}, is_correction=False
    )
    assert blocked == []
    assert to_set == {"background": "fils de légionnaire"}


@modeling_quality_suite.test()
def test_same_value_not_blocked() -> None:
    """Re-poser la même valeur n'est pas un écrasement (idempotent)."""
    to_set, blocked = plan_property_update(
        {"age": "40 ans"}, {"age": "40 ans"}, is_correction=False
    )
    assert blocked == []
    assert to_set == {"age": "40 ans"}


@modeling_quality_suite.test()
def test_empty_existing_not_blocked() -> None:
    """Remplir une clé vide/absente n'écrase rien."""
    to_set, blocked = plan_property_update(
        {"traits": ""}, {"traits": "colonial pur suif"}, is_correction=False
    )
    assert blocked == []
    assert to_set == {"traits": "colonial pur suif"}
