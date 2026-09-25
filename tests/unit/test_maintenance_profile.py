"""Profil maintenance (Étape 1.1 du plan) — vocab structurel + chroniqueur coupé.

Univers de TEST : sertisseuse SX-40 (fixture synthétique, cf.
[[feedback_prompt_test_leakage]]) — distinct de la presse plieuse PL-7 utilisée
dans les exemples des prompts, jamais l'inverse.
"""
from __future__ import annotations

from protest import ProTestSuite

from felix.atelier.agent import ATELIER_CHOICES
from felix.core.profile import (
    CHANTIER_PROFILE,
    MAINTENANCE_PROFILE,
    SCENARIO_PROFILE,
    runs_chronicle,
)

maintenance_profile_suite = ProTestSuite("MaintenanceProfile")

P = MAINTENANCE_PROFILE

ENTITY_TYPES = ("machine", "organe", "commande", "parametre", "mode", "consigne", "document")


# ──────────────────── validate_relation ────────────────────
@maintenance_profile_suite.test()
def test_controls_commande_to_parametre_ok() -> None:
    """Le sélecteur de force CONTROLS le paramètre pression_sertissage (SX-40)."""
    assert P.validate_relation("CONTROLS", "commande", "parametre", same_node=False) is None


@maintenance_profile_suite.test()
def test_controls_parametre_to_commande_rejected() -> None:
    """Sens inverse refusé : un paramètre ne « commande » pas un bouton."""
    assert P.validate_relation("CONTROLS", "parametre", "commande", same_node=False)


@maintenance_profile_suite.test()
def test_non_vocab_type_rejected_with_guiding_message() -> None:
    """Un type hors vocabulaire (inventé) est refusé avec un message qui liste
    les types STRUCTURELS exacts du domaine (dont CONTROLS)."""
    msg = P.validate_relation("MONITORS", "commande", "organe", same_node=False)
    assert msg and "CONTROLS" in msg


@maintenance_profile_suite.test()
def test_described_in_is_code_only() -> None:
    """DESCRIBED_IN est réservée au code (posée par link_described_in à
    l'ingestion, #Étape 2) — validate_relation reste permissif (typage
    structurel), c'est add_relation (le tool LLM) qui la refuse (cf.
    tests/unit/test_ingest_document.py)."""
    assert "DESCRIBED_IN" in P.code_only_relations


@maintenance_profile_suite.test()
def test_described_in_every_declared_type_to_document_ok() -> None:
    """DESCRIBED_IN — posée par le code à l'ingestion — accepte chacun des types
    déclarés du domaine comme sujet, document comme cible."""
    for entity_type in ENTITY_TYPES:
        assert P.validate_relation(
            "DESCRIBED_IN", entity_type, "document", same_node=False
        ) is None, entity_type


@maintenance_profile_suite.test()
def test_applies_to_consigne_to_organe_ok() -> None:
    """« ne jamais dépasser 12 kN sur la mâchoire » — consigne APPLIES_TO organe
    (la mâchoire de la SX-40)."""
    assert P.validate_relation("APPLIES_TO", "consigne", "organe", same_node=False) is None


# ──────────────────── render_prompt_block ────────────────────
@maintenance_profile_suite.test()
def test_prompt_block_lists_every_entity_type() -> None:
    block = P.render_prompt_block()
    for entity_type in ENTITY_TYPES:
        assert f"- {entity_type} :" in block, entity_type


# ──────────────────── runs_chronicle ────────────────────
@maintenance_profile_suite.test()
def test_runs_chronicle_false_for_maintenance() -> None:
    assert runs_chronicle(MAINTENANCE_PROFILE) is False


@maintenance_profile_suite.test()
def test_runs_chronicle_false_for_chantier() -> None:
    assert runs_chronicle(CHANTIER_PROFILE) is False


@maintenance_profile_suite.test()
def test_runs_chronicle_false_for_none() -> None:
    assert runs_chronicle(None) is False


@maintenance_profile_suite.test()
def test_runs_chronicle_true_for_scenario() -> None:
    assert runs_chronicle(SCENARIO_PROFILE) is True


# ──────────────────── AgentChoice — prompts par profil ────────────────────
@maintenance_profile_suite.test()
def test_maintenance_choice_has_distinct_master_prompt() -> None:
    maintenance = ATELIER_CHOICES["maintenance"]
    scenario = ATELIER_CHOICES["scenario"]
    assert maintenance.master_prompt.strip()
    assert maintenance.master_prompt != scenario.master_prompt
    assert "documentation" in maintenance.master_prompt.lower()


@maintenance_profile_suite.test()
def test_maintenance_choice_has_distinct_gate_prompt() -> None:
    maintenance = ATELIER_CHOICES["maintenance"]
    scenario = ATELIER_CHOICES["scenario"]
    assert maintenance.gate_prompt.strip()
    assert maintenance.gate_prompt != scenario.gate_prompt
    assert "technique" in maintenance.gate_prompt.lower()
