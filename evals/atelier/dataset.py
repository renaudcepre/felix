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
    char_props,
    entity_unique,
    events_distinct,
    events_involve,
    events_ordered,
    graph_char_count,
    graph_has_characters,
    graph_has_entities,
    graph_has_events,
    involves_only_entities,
    no_tool_cards,
    rel_vocab_coverage,
    relations_present,
    relations_skip_events,
)

# Scénario complet « La Roue de Sang » (steampunk noir) joué beat par beat sur le
# même graphe : teste l'extraction cumulative, la résolution (Silas = 1 nœud sur
# 7 tours) et les relations clés. Représente l'usage réel « je raconte au fil de
# l'eau » plutôt qu'un message isolé.
_roue_de_sang_beats = [
    "Néo-Londres, 1899 alternatif. Le ciel est une chape de plomb striée par des "
    "zeppelins militaires. Silas, un détective privé désabusé doté d'un bras "
    "mécanique à vapeur, examine un cadavre dans les bas-fonds. La victime n'a plus "
    "de sang : il a été remplacé par une huile noire visqueuse, et son cœur "
    "mécanique bat encore, gravé de runes occultes.",
    "Silas tente d'apporter les preuves à la Milice du Cuivre. Son supérieur lui "
    "ordonne d'étouffer l'affaire et lui confisque les pièces à conviction. Silas "
    "comprend que la corruption dépasse la simple pègre locale. En sortant, il est "
    "attaqué par des « Golems de suie », des colosses de métal animés par de la "
    "nécromancie. Il s'échappe de justesse grâce à la surcharge de son bras.",
    "Silas remonte la piste de l'huile noire jusqu'à une fonderie clandestine dans "
    "les niveaux inférieurs de la ville. Là, il découvre l'horreur : des ouvriers "
    "disparus sont enchaînés à des machines rituelles. Des mages noirs en tablier "
    "de cuir et masques à gaz drainent leur essence vitale pour forger de "
    "« l'Athanor », un carburant magico-mécanique surpuissant.",
    "Silas est repéré. Alors qu'il est sur le point d'être capturé, il est sauvé "
    "par Éléonore, une ingénieure rebelle qui utilise une magie runique « propre » "
    "(liée à la pression de l'eau). Elle lui révèle la vérité : la Grande Chaudière "
    "Centrale, qui chauffe toute la mégapole, va être convertie à l'Athanor lors de "
    "la prochaine éclipse de Lune, ce qui transformera la ville en autel sacrificiel.",
    "Pour arrêter le rituel, Silas et Éléonore doivent saboter le Vapor-Dominus, le "
    "zeppelin-forteresse du Grand Mage Industriel, le Baron Arkham. Ils infiltrent "
    "les docks suspendus au milieu d'une tempête de grêle. Mais Éléonore est "
    "capturée sous les yeux de Silas, qui doit fuir en sautant dans le vide, sauvé "
    "par son grappin pneumatique.",
    "L'Éclipse commence. Le ciel devient rouge sang. Silas assaille le Vapor-Dominus "
    "en solo, utilisant les conduits de vapeur pour se faufiler. Il atteint la salle "
    "du réacteur où Arkham s'apprête à sacrifier Éléonore. Un duel s'engage au "
    "milieu des pistons géants. Silas sacrifie son bras cybernétique pour bloquer "
    "l'engrenage principal du rituel.",
    "Le réacteur explose, détruisant le zeppelin. Silas et Éléonore s'échappent en "
    "parachute alors que la forteresse volante s'écrase dans les quartiers riches. "
    "La ville est sauvée de l'annihilation, mais la Grande Chaudière est détruite : "
    "le gel commence à s'installer sur Néo-Londres.",
]

# Scénario d'ACTION pur (3 beats) : un même personnage enchaîne trois gestes
# distincts. Aujourd'hui l'agent fourre l'action dans une prop `action`/`etat`
# écrasée à chaque beat → la chronologie est perdue (verrue « Le Nadir »). Le
# modèle événementiel doit produire 3 nodes evenement ORDONNÉS reliés au perso,
# pas trois écrasements d'une même prop.
_action_beats = [
    "Le capitaine Vance fait irruption sur la passerelle et tire sur les consoles "
    "de navigation pour saboter le vaisseau.",
    "Vance verrouille l'écoutille de secours pour piéger l'équipage à l'intérieur.",
    "Vance traîne la mercenaire blessée jusqu'à la capsule de sauvetage.",
]

# Reproduction des bugs trouvés en live (« Le Nadir ») : un tour DESCRIPTIF (pose
# le décor, Vance présent, peu/pas d'action) PUIS un tour à événements. Révèle ce
# que `_action_beats` (3 actions nettes) ne montrait pas : (1) le chroniqueur qui
# re-chronique le tour 1 au tour 2 (il voyait l'historique) → doublons ; (2)
# add_event résolvant un participant vers le node événement lui-même (auto-INVOLVES).
_nadir_beats = [
    "Le Nadir, un cargo-benne usé jusqu'à la corde, dérive en silence dans un "
    "secteur mort. Vance, le chef de la sécurité — un flic fatigué en fin de "
    "contrat — traîne ses bottes dans les coursives vides.",
    "L'IA de bord lance une alerte : le bilan de masse est faussé, 82 kilos de "
    "trop non répertoriés à bord. Les capteurs thermiques de la soute 4 "
    "s'éteignent un par un, comme si une ombre avançait en coupant les fils.",
]

# Seed partagé des cas de check : Marco (alibi à Marseille le 12 juin) et le
# Vesuvio localisé à Lyon — sans l'adresse, Marseille vs « au Vesuvio » ne serait
# pas une contradiction démontrable (leçon des evals generic).
_check_seed = [
    {"name": "Marco Santi",
     "props": {"alibi": "chez sa mère à Marseille le soir du 12 juin"}},
    {"name": "Le Vesuvio", "entity_type": "lieu",
     "props": {"adresse": "8 quai de Bondy, Lyon"}},
]

# Seed partagé des deux cas « checker temporel » (mort-puis-agit). Borin est un
# garde, le Baron son maître, la salle du trône le décor — entités stables pour
# que le chroniqueur résolve les participants des events au lieu d'en créer.
_garde_seed = [
    {"name": "Borin", "props": {"role": "garde du corps du Baron Arkham"}},
    {"name": "Le Baron Arkham", "props": {"role": "seigneur du château"}},
    {"name": "La salle du trône", "entity_type": "lieu",
     "props": {"description": "la grande salle du château d'Arkham"}},
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
        # Baptême différé (bug Adator, dogfood 2026-06-10) : une entité suivie SANS
        # vrai nom (« un mage noir ») reçoit son nom DEUX TOURS plus tard. Attendu :
        # rename_entity sur la fiche existante → UN seul personnage, nommé Alikazeth.
        # Échec historique : fiche neuve « Alikazeth » + « Mage Noir » orpheline (la
        # passe 1 ne relit pas la base ; le working set injecté doit la lui montrer).
        EvalCase(
            name="bapteme_differe",
            inputs={
                "beats": [
                    "Un mage noir a pris le pouvoir dans la ville d'Adator, par la ruse.",
                    "Le mage noir se nomme « Alikazeth ».",
                ],
                "seed": [],
            },
            evaluators=[
                graph_char_count(n=1),
                entity_unique(names="Alikazeth"),
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
        # --- overwrite vs add (règle 4 : diverge → ajoute, corrige → remplace) ---
        EvalCase(
            name="diverge_adds_keeps_old",
            inputs={
                "message": "Ajoute que Marco était au Vesuvio, à Lyon, le soir du 12 juin.",
                "seed": [
                    {"name": "Marco Santi",
                     "props": {"alibi": "chez sa mère à Marseille le soir du 12 juin"}},
                ],
            },
            # Fait divergent (autre lieu, même soir) → s'AJOUTE sans écraser l'alibi :
            # les DEUX doivent finir dans les props de Marco (ancien + nouveau).
            evaluators=[char_props(name="Marco Santi", has="marseille, lyon")],
        ),
        EvalCase(
            name="explicit_correction_overwrites",
            inputs={
                "message": "Correction : en fait l'alibi de Marco Santi, c'était Lyon, pas Marseille.",
                "seed": [
                    {"name": "Marco Santi",
                     "props": {"alibi": "chez sa mère à Marseille le soir du 12 juin"}},
                ],
            },
            # Correction explicite (« correction », « en fait ») → REMPLACE.
            evaluators=[char_props(name="Marco Santi", has="lyon", hasnt="marseille")],
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
        # --- checker TEMPOREL (mort-puis-agit) : A/B, même graphe final, ordre
        # INVERSÉ. Prouve que le verdict repose sur l'ORDRE des événements (la
        # chronologie dérivée), pas sur la coprésence « mort + action ». ---
        EvalCase(
            name="check_death_then_act",
            inputs={
                "beats": [
                    "Le Baron Arkham dégaine et abat Borin d'une balle en plein "
                    "cœur ; le garde s'effondre, mort, sur les dalles de la salle "
                    "du trône.",
                    "Plus tard, Borin se relève, verrouille la lourde porte "
                    "blindée de la salle et coupe les communications du château.",
                ],
                "seed": _garde_seed,
                "check": "borin",
            },
            # Mort (#1) PUIS action propre de Borin (#2) → impossibilité
            # temporelle : un mort ne peut plus agir. Alerte attendue.
            evaluators=[alert_emitted(expected=True)],
        ),
        EvalCase(
            name="check_act_then_death",
            inputs={
                "beats": [
                    "Borin verrouille la lourde porte blindée de la salle du "
                    "trône et coupe les communications du château.",
                    "Plus tard, Le Baron Arkham dégaine et abat Borin d'une balle "
                    "en plein cœur ; le garde s'effondre, mort, sur les dalles.",
                ],
                "seed": _garde_seed,
                "check": "borin",
            },
            # MÊMES faits, ordre inversé : action (#1) AVANT la mort (#2) → normal.
            # Garde anti-lecture-naïve : même si `statut='mort'` finit posé sur
            # Borin, l'action lui est ANTÉRIEURE → aucune alerte.
            evaluators=[alert_emitted(expected=False)],
        ),
        # --- scénario complet multi-beats (extraction cumulative + résolution) ---
        EvalCase(
            name="roue_de_sang",
            inputs={"beats": _roue_de_sang_beats, "seed": []},
            evaluators=[
                # extraction cumulative : les entités phares sont présentes (souple)
                graph_has_entities(
                    ids="silas, eleonore, arkham, athanor, fonderie, golems, mages, "
                        "milice, grande chaudiere, vapor-dominus, eclipse",
                    min_recall=0.8,
                ),
                # résolution : les 2 leads = UN seul nœud sur 7 beats. Noms propres
                # stables (match exact) ; on omet « Baron Arkham » dont la forme de
                # surface varie (Arkham / Le Baron Arkham) et ferait flaker l'exact.
                entity_unique(names="Silas, Éléonore"),
                # relations clés (sens ignoré, ids souples). Seuil ASPIRATIONNEL :
                # l'extraction de relations est la dimension faible aujourd'hui
                # (~60-80 % selon les runs, noms qui dérivent). On garde la barre
                # haute comme cible — l'améliorer est le prochain chantier, pas la
                # baisser pour faire passer (cf. evals aspirationnelles Felix).
                relations_present(
                    pairs="silas->cadavre, mages->athanor, mages->ouvriers, "
                          "eleonore->silas, silas->arkham",
                    min_recall=0.8,
                ),
                # Dérive des noms de relations : métrique-only (ne gate pas encore).
                rel_vocab_coverage(min_coverage=0.0),
                # Hygiène événements : pas de doublon, pas de relation entité↔event.
                events_distinct,
                relations_skip_events,
            ],
        ),
        # --- modèle événementiel (chronologie des actions, pas d'écrasement) ---
        EvalCase(
            name="event_chrono",
            inputs={"beats": _action_beats, "seed": []},
            evaluators=[
                # Chaque geste = un node evenement (resume contient l'action), pas
                # une prop écrasée. Seuil souple (extraction = dimension neuve).
                graph_has_events(resumes="tire, verrouille, traine", min_recall=0.66),
                # Chronologie : >= 3 events, ordre distinct, chaîne NEXT complète.
                events_ordered(min_count=3),
                # Participants : la plupart des events relient Vance via INVOLVES
                # (sous-chaîne souple : « Vance » ⊂ « Capitaine Vance »).
                events_involve(who="Vance", min_recall=0.66),
            ],
        ),
        # --- bugs live « Le Nadir » : pas de re-chroniquage ni d'auto-INVOLVES ---
        EvalCase(
            name="event_no_bleed",
            inputs={"beats": _nadir_beats, "seed": []},
            evaluators=[
                # Au moins l'événement du tour 2 (alerte IA / capteurs), chaîne saine.
                events_ordered(min_count=1),
                # Pas de doublon : le tour 2 ne doit pas recréer le décor du tour 1.
                events_distinct,
                # Aucun INVOLVES vers un event (auto-référence du bug live).
                involves_only_entities,
                # Aucune relation entité↔event (relieur qui relie des actions).
                relations_skip_events,
            ],
        ),
    ]
)
