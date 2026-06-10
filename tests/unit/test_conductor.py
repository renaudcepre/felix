"""Chef d'orchestre (maître + gate) — garanties STRUCTURELLES du routage.

Le maître (passe 0) MÈNE la conversation ; la DÉCISION d'extraire est portée par
le gate stateless (RouteDecision). Garanties clés, vérifiées ici sans LLM :
- le maître est en LECTURE SEULE → l'hallucination « salut → invente une entité »
  est impossible PAR CONSTRUCTION ;
- le gate est reason-first (le fait AVANT le booléen) — la propriété qui fait
  trancher Small en connaissance de cause ;
- les univers des TESTS (conductor_e2e, evals) n'apparaissent pas dans les
  prompts de routage (cf. feedback_prompt_test_leakage) — sinon la mesure du
  routage est triviale.
La décision comportementale, elle, est mesurée par `just e2e-conductor`.
"""
from __future__ import annotations

import re

from protest import ProTestSuite

from felix.atelier.agent import (
    GATE_SYSTEM_PROMPT,
    MASTER_SYSTEM_PROMPT,
    MASTER_TOOLS,
    RouteDecision,
)
from felix.core.deps import GenericDeps

conductor_suite = ProTestSuite("Conductor")

WRITE_TOOLS = {"add_entity", "update_entity", "add_relation", "add_event", "rename_entity"}

# Univers utilisés par les TESTS du routage (conductor_e2e : sessions mêlée et
# ornière ; evals : bapteme_differe). S'ils entrent dans un prompt, le test ne
# mesure plus rien — le modèle récite au lieu de généraliser.
TEST_UNIVERSES = ("Nora", "Castan", "Port-Vendres", "Veil",
                  "Vada", "Tilio", "Sorne",
                  "Adator", "Alikazeth")


@conductor_suite.test()
def test_master_has_no_write_tools() -> None:
    """Le maître n'a AUCUN outil d'écriture → il ne peut pas inventer d'entité."""
    names = {t.__name__ for t in MASTER_TOOLS}
    assert names & WRITE_TOOLS == set(), f"le maître a des outils d'écriture : {names & WRITE_TOOLS}"


@conductor_suite.test()
def test_master_is_read_only() -> None:
    """Lecture de la bible UNIQUEMENT : la décision d'extraire vit dans le gate,
    pas dans le fil threadé (sinon retour de l'ornière d'auto-imitation, #43)."""
    names = {t.__name__ for t in MASTER_TOOLS}
    assert names == {"find_entity", "list_entities"}, f"outils inattendus : {names}"


@conductor_suite.test()
def test_gate_decision_is_reason_first() -> None:
    """RouteDecision génère `fait` AVANT `noter` : le modèle formule le fait puis
    tranche — inverser ferait trancher Small à l'aveugle."""
    assert list(RouteDecision.model_fields) == ["fait", "noter"]


@conductor_suite.test()
def test_no_test_universe_leaks_into_prompts() -> None:
    """Les univers des tests de routage n'entrent JAMAIS dans les prompts.
    Match sur MOT ENTIER : « Veil » ne doit pas matcher dans « surveille »."""
    prompts = GATE_SYSTEM_PROMPT + MASTER_SYSTEM_PROMPT
    leaked = [
        name for name in TEST_UNIVERSES
        if re.search(rf"\b{re.escape(name)}\b", prompts, re.IGNORECASE)
    ]
    assert not leaked, f"univers de test présents dans les prompts : {leaked}"


@conductor_suite.test()
def test_extraction_flag_defaults_false() -> None:
    """Sans verdict du gate, on n'extrait pas : le flag par défaut est faux."""
    deps = GenericDeps(driver=None)  # type: ignore[arg-type]  # pas de driver pour ce test pur
    assert deps.extraction_requested is False
