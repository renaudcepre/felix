"""Chef d'orchestre (maître) — garanties STRUCTURELLES du routage d'extraction.

Le maître (passe 0) MÈNE la conversation et décide s'il faut extraire. Garantie clé,
vérifiée ici sans LLM : son jeu d'outils est en LECTURE SEULE + l'outil-signal — il
ne PEUT pas écrire dans la base, donc l'hallucination « salut → invente une entité »
est impossible PAR CONSTRUCTION (la décision comportementale, elle, est mesurée par la
sonde de routage LLM). Le flag `extraction_requested` gate les extracteurs côté route.
"""
from __future__ import annotations

from protest import ProTestSuite

from felix.atelier.agent import MASTER_TOOLS
from felix.core.deps import GenericDeps

conductor_suite = ProTestSuite("Conductor")

WRITE_TOOLS = {"add_entity", "update_entity", "add_relation", "add_event", "rename_entity"}


@conductor_suite.test()
def test_master_has_no_write_tools() -> None:
    """Le maître n'a AUCUN outil d'écriture → il ne peut pas inventer d'entité."""
    names = {t.__name__ for t in MASTER_TOOLS}
    assert names & WRITE_TOOLS == set(), f"le maître a des outils d'écriture : {names & WRITE_TOOLS}"


@conductor_suite.test()
def test_master_has_read_and_signal_tools() -> None:
    """Il garde la LECTURE de la bible (répondre aux questions) + l'outil-signal."""
    names = {t.__name__ for t in MASTER_TOOLS}
    assert {"find_entity", "list_entities", "noter_le_passage"} <= names


@conductor_suite.test()
def test_extraction_flag_defaults_false() -> None:
    """Sans signal, on n'extrait pas : le flag par défaut est faux (gate fermé)."""
    deps = GenericDeps(driver=None)  # type: ignore[arg-type]  # pas de driver pour ce test pur
    assert deps.extraction_requested is False
