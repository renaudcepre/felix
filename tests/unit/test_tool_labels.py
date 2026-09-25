"""Libellés humains des tools (#78) — TDD red→green.

Le LLM n'écrit jamais de Cypher : son langage de requête, ce sont les appels
d'outil (find_entity, add_relation…). Chaque tool déclare son gabarit de
libellé À CÔTÉ de sa définition (`felix.core.tools.tool_label`), dans le
registre UNIQUE `TOOL_LABELS` — jamais une table à part qui dérive du code
réel. Le test structurel construit les VRAIS agents de l'app (maître,
extracteurs, chroniqueur — le gate n'a aucun tool) et vérifie que chaque tool
qu'ils enregistrent a un libellé, pour qu'un tool ajouté sans libellé fasse
échouer la suite plutôt que de s'afficher vide en prod.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from protest import ProTestSuite

if TYPE_CHECKING:
    from pydantic_ai import Agent

from felix.atelier.agent import (
    ATELIER_CHOICES,
    build_atelier_agent,
    build_chronicle_agent,
    build_master_agent,
    build_relation_agent,
)
from felix.core.tools import TOOL_LABELS, label_for_tool_call

tool_labels_suite = ProTestSuite("ToolLabels")


# ─────────── structurel : tout tool enregistré sur un agent de l'app a un libellé ───────────

def _agents_built_by_the_app() -> dict[str, Agent[Any, Any]]:
    """Les agents PORTEURS de tools construits par felix.atelier.agent — le gate
    (build_gate_agent) est délibérément absent : `output_type=RouteDecision`,
    aucun tool, rien à labelliser. Un seul choix de profil suffit : les tools
    d'un agent ne dépendent pas du profil de domaine (seules les instructions
    en dépendent), cf. felix.atelier.agent.build_*_agent."""
    choice = ATELIER_CHOICES["scenario"]
    return {
        "maître": build_master_agent(choice),
        "extracteur entités": build_atelier_agent(choice),
        "relieur": build_relation_agent(choice),
        "chroniqueur": build_chronicle_agent(choice),
    }


@tool_labels_suite.test()
def test_every_tool_registered_on_an_app_agent_has_a_label() -> None:
    for agent_name, agent in _agents_built_by_the_app().items():
        registered = agent._function_toolset.tools
        assert registered, f"{agent_name} n'a enregistré aucun tool (agent mal construit ?)"
        for tool_name in registered:
            assert tool_name in TOOL_LABELS, (
                f"tool « {tool_name} » enregistré sur « {agent_name} » sans "
                "libellé humain — ajoute @tool_label(...) au-dessus de sa "
                "définition dans felix/core/tools.py"
            )


# ─────────── label_for_tool_call : gabarits + repli gracieux ───────────

@tool_labels_suite.test()
def test_find_entity_label_uses_name_arg() -> None:
    label = label_for_tool_call("find_entity", {"name": "Zorvun"})
    assert label == "Recherche d'informations sur Zorvun"


@tool_labels_suite.test()
def test_list_entities_label_is_static() -> None:
    assert label_for_tool_call("list_entities", {}) == "Liste des fiches"


@tool_labels_suite.test()
def test_add_entity_label_uses_name_arg() -> None:
    label = label_for_tool_call(
        "add_entity", {"name": "Kelphi", "entity_type": "personnage"}
    )
    assert label == "Création de la fiche Kelphi"


@tool_labels_suite.test()
def test_update_entity_label_uses_name_arg() -> None:
    label = label_for_tool_call("update_entity", {"name": "Zorvun", "props": {}})
    assert label == "Mise à jour de la fiche Zorvun"


@tool_labels_suite.test()
def test_add_relation_label_prefers_verbe_over_rel_type() -> None:
    label = label_for_tool_call("add_relation", {
        "from_name": "Zorvun", "to_name": "Kelphi",
        "rel_type": "LIE_A", "verbe": "protège",
    })
    assert label == "Lien « protège » entre Zorvun et Kelphi"


@tool_labels_suite.test()
def test_add_relation_label_falls_back_to_rel_type_without_verbe() -> None:
    label = label_for_tool_call("add_relation", {
        "from_name": "Zorvun", "to_name": "Kelphi",
        "rel_type": "MEMBER_OF", "verbe": "",
    })
    assert label == "Lien « MEMBER_OF » entre Zorvun et Kelphi"


@tool_labels_suite.test()
def test_add_event_label_uses_resume_arg() -> None:
    label = label_for_tool_call("add_event", {"resume": "Zorvun franchit le seuil"})
    assert label == "Événement : Zorvun franchit le seuil"


@tool_labels_suite.test()
def test_move_event_label_uses_resume_arg() -> None:
    label = label_for_tool_call(
        "move_event", {"resume": "Zorvun franchit le seuil", "position": "avant", "reference": "x"}
    )
    assert label == "Déplacement de l'événement « Zorvun franchit le seuil »"


@tool_labels_suite.test()
def test_missing_arg_is_graceful_not_a_crash() -> None:
    """Un arg manquant (tool appelé sans un param optionnel, ou args partiels
    dans un test/eval) ne doit JAMAIS lever — repli sur une chaîne vide."""
    label = label_for_tool_call("find_entity", {})
    assert label == "Recherche d'informations sur "


@tool_labels_suite.test()
def test_unknown_tool_falls_back_to_its_raw_name() -> None:
    label = label_for_tool_call("un_tool_jamais_enregistre", {"x": 1})
    assert label == "un_tool_jamais_enregistre"
