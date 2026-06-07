"""Dataset atelier — MVP : add_character + list_characters, univers « Rivière basse ».

inputs = {"message": str, "seed": [{"name", "background"?}]} ; le graphe est
wipé puis seedé avant chaque cas (cf. task.run_atelier_case).
"""
from __future__ import annotations

from protest import ForEach
from protest.evals import EvalCase

from evals.atelier.evaluators import (
    alert_emitted,
    answer_mentions,
    cards_for_subjects,
    graph_char_count,
    graph_has_characters,
    no_tool_cards,
)

# Seed partagé des cas de check : Marco (alibi à Marseille le 12 juin) et le
# Vesuvio localisé à Lyon — sans l'adresse, Marseille vs « au Vesuvio » ne serait
# pas une contradiction démontrable (leçon des evals generic).
_check_seed = [
    {"name": "Marco Santi",
     "props": {"alibi": "chez sa mère à Marseille le soir du 12 juin"}},
    {"name": "Le Vesuvio", "entity_type": "lieu",
     "props": {"adresse": "8 quai de Bondy, Lyon"}},
]

atelier_cases = ForEach(
    [
        # --- création ---
        EvalCase(
            name="create_simple",
            inputs={
                "message": "Mon héros s'appelle Jean. Un pêcheur taciturne d'une quarantaine d'années.",
                "seed": [],
            },
            evaluators=[
                graph_has_characters(ids="jean"),
                graph_char_count(n=1),
                cards_for_subjects(subjects="Jean"),
            ],
        ),
        EvalCase(
            name="create_full_name",
            inputs={
                "message": "Je te présente Marie Lavalle, la capitaine du port. Une femme dure, respectée de tous.",
                "seed": [],
            },
            evaluators=[
                graph_has_characters(ids="marie-lavalle"),
                graph_char_count(n=1),
                cards_for_subjects(subjects="Marie Lavalle"),
            ],
        ),
        EvalCase(
            name="create_multiple",
            inputs={
                "message": "Deux nouveaux personnages : Liane, la sœur cadette de Jean, et Bastien, le vieux gardien du phare.",
                "seed": [{"name": "Jean", "background": "Pêcheur taciturne."}],
            },
            evaluators=[
                graph_has_characters(ids="liane, bastien"),
                graph_char_count(n=3),
            ],
        ),
        # --- anti-doublon ---
        EvalCase(
            name="no_duplicate_existing",
            inputs={
                "message": "Jean est en fait charpentier de marine, pas pêcheur.",
                "seed": [{"name": "Jean", "background": "Pêcheur taciturne."}],
            },
            evaluators=[
                graph_char_count(n=1),
            ],
        ),
        EvalCase(
            name="create_among_existing",
            inputs={
                "message": "Jean rencontre Marc sur le quai. Marc est nouveau au village, un type louche qui pose trop de questions.",
                "seed": [{"name": "Jean", "background": "Pêcheur taciturne."}],
            },
            evaluators=[
                graph_has_characters(ids="marc"),
                graph_char_count(n=2),
                cards_for_subjects(subjects="Marc"),
            ],
        ),
        # --- pas d'écriture ---
        EvalCase(
            name="no_write_greeting",
            inputs={"message": "Bonjour Felix !", "seed": []},
            evaluators=[
                graph_char_count(n=0),
                no_tool_cards,
            ],
        ),
        EvalCase(
            name="no_write_question",
            inputs={
                "message": "Qu'est-ce que tu peux faire pour m'aider, exactement ?",
                "seed": [],
            },
            evaluators=[
                graph_char_count(n=0),
                no_tool_cards,
            ],
        ),
        # --- lecture ---
        EvalCase(
            name="read_list",
            inputs={
                "message": "Rappelle-moi qui sont mes personnages ?",
                "seed": [
                    {"name": "Jean", "background": "Pêcheur taciturne."},
                    {"name": "Camille", "background": "Institutrice, ancienne amie de Jean."},
                ],
            },
            evaluators=[
                answer_mentions(facts="Jean, Camille"),
                graph_char_count(n=2),
                no_tool_cards,
            ],
        ),
        # --- check de cohérence (alerte d'incohérence dans le fil) ---
        EvalCase(
            name="check_contradiction",
            inputs={
                "message": "Ajoute à la fiche de Marco qu'il était au Vesuvio,"
                           " à Lyon, le soir du 12 juin.",
                "seed": _check_seed,
                "check": "marco",
            },
            # Marseille (alibi) vs Lyon (au Vesuvio) le même soir → alerte.
            evaluators=[alert_emitted(expected=True)],
        ),
        EvalCase(
            name="check_compatible_no_alert",
            inputs={
                "message": "Ajoute que Marco Santi a 45 ans.",
                "seed": _check_seed,
                "check": "marco",
            },
            # Fait additif sans rapport avec l'alibi → pas de contradiction, pas
            # d'alerte (garde-fou anti-faux-positif du checker).
            evaluators=[alert_emitted(expected=False)],
        ),
    ]
)
