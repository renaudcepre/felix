"""Dataset generic-core — 3 domaines (abri bois / polar / WW2), même code.

Ce que chaque groupe mesure :
- *_create        : extraction libre → entités/props/relations sensées
- *_key_reuse     : discipline de schéma émergent — intra-conversation
                    (la clé vient du tour 1) et inter-session (la clé vient
                    du seed, découvrable uniquement via describe_schema)
- check_*         : cohérence « voisinage + judge » sans sémantique codée —
                    contradiction directe, via une relation, et le miroir
                    compatible (anti-faux-positif, la plaie historique du 7B)
"""
from __future__ import annotations

from protest import ForEach
from protest.evals import EvalCase

from evals.generic.evaluators import (
    check_verdict,
    count_matching,
    entities_exist,
    has_prop_keys,
    has_prop_value,
    no_entities,
    prop_key_shared,
    relation_between,
    same_entity_type,
)

atelier_seed_dalle = {
    "entities": [
        {"name": "dalle béton", "entity_type": "ouvrage", "props": {"largeur": "3 m", "longueur": "4 m"}},
        {"name": "abri de jardin", "entity_type": "ouvrage", "props": {}},
    ],
    "relations": [{"from": "abri de jardin", "to": "dalle béton", "rel_type": "pose_sur"}],
}

# ── seeds « échelle » ──
# Gros voisinage polar : la contradiction (alibi de Marco) devra être trouvée
# au milieu de 14 personnages liés, chacun avec rôle + alibi (needle in haystack).
_ENTOURAGE = [
    ("Antoine Berger", "barman au Vesuvio", "en service au club jusqu'à 2h"),
    ("Sofia Keller", "comptable du club", "chez elle à Caluire"),
    ("Karim Aydin", "videur", "en service au club"),
    ("Jeanne Maury", "serveuse", "en congé, chez sa sœur à Grenoble"),
    ("Paulo Ferreira", "fournisseur de spiritueux", "tournée à Saint-Étienne"),
    ("Nadia Boulif", "DJ résidente", "mix au club jusqu'à 3h"),
    ("Victor Lemoine", "habitué, joueur de poker", "au cercle de jeu rue Mercière"),
    ("Estelle Roy", "ex-compagne de Marco", "week-end à Annecy"),
    ("Bruno Castel", "associé minoritaire", "dîner d'affaires aux Brotteaux"),
    ("Inès Da Costa", "femme de ménage", "service terminé à 19h"),
    ("Théo Marchand", "livreur", "dernière livraison à 18h30"),
    ("Lucie Brun", "voisine du club", "chez elle, a entendu du bruit"),
    ("Samir Nasri", "prêteur sur gages", "introuvable ce soir-là"),
    ("Hélène Vasseur", "avocate de Marco", "gala au palais de la Bourse"),
]
big_noir_seed = {
    "entities": [
        {"name": "Marco Santi", "entity_type": "personnage",
         "props": {"role": "suspect principal",
                   "alibi": "chez sa mère à Marseille le soir du 12 juin",
                   "adresse": "12 rue Moncey, Lyon"}},
        {"name": "Le Vesuvio", "entity_type": "lieu",
         "props": {"adresse": "8 quai de Bondy, Lyon", "categorie": "club de nuit"}},
        *[{"name": n, "entity_type": "personnage", "props": {"role": r, "alibi": a}}
          for n, r, a in _ENTOURAGE],
    ],
    "relations": [
        {"from": "Marco Santi", "to": "Le Vesuvio", "rel_type": "gerant_de"},
        *[{"from": "Marco Santi", "to": n, "rel_type": "connait"} for n, _, _ in _ENTOURAGE],
    ],
}

# Schéma riche multi-types : la bonne clé (prix, date_achat, fournisseur…)
# devra être retrouvée au milieu d'une vingtaine de clés réparties sur 4 types.
chantier_seed = {
    "entities": [
        {"name": "perceuse Bosch GSB", "entity_type": "outil",
         "props": {"date_achat": "2023", "prix": "129 euros", "fournisseur": "Leroy Merlin"}},
        {"name": "marteau XP-55", "entity_type": "outil",
         "props": {"date_achat": "2022", "prix": "25 euros"}},
        {"name": "visseuse Makita DDF485", "entity_type": "outil",
         "props": {"date_achat": "2021", "etat": "batterie fatiguée"}},
        {"name": "bastaings 60x180", "entity_type": "materiau",
         "props": {"essence": "douglas", "quantite": "12", "fournisseur": "scierie Martin",
                   "prix": "340 euros", "date_achat": "avril 2024"}},
        {"name": "panneaux OSB 18mm", "entity_type": "materiau",
         "props": {"quantite": "8", "prix": "210 euros", "fournisseur": "Brico Dépôt"}},
        {"name": "dalle béton", "entity_type": "ouvrage",
         "props": {"largeur": "3 m", "longueur": "4 m", "epaisseur": "12 cm",
                   "date_coulage": "mars 2024"}},
        {"name": "abri de jardin", "entity_type": "ouvrage",
         "props": {"surface": "9 m2", "hauteur_faitage": "2,4 m"}},
        {"name": "Paul Vidal", "entity_type": "personne",
         "props": {"role": "maçon", "telephone": "06 11 22 33 44", "tarif_jour": "280 euros"}},
    ],
    "relations": [
        {"from": "abri de jardin", "to": "dalle béton", "rel_type": "pose_sur"},
    ],
}

generic_cases = ForEach(
    [
        # ───────── domaine 1 : montage d'un abri bois (technique) ─────────
        EvalCase(
            name="wood_create",
            inputs={"messages": ["J'ai un marteau XP-55, acheté en 2022."]},
            evaluators=[entities_exist(names="marteau")],
        ),
        EvalCase(
            name="wood_key_reuse_conversation",
            inputs={
                "messages": [
                    "J'ai un marteau XP-55, acheté en 2022.",
                    "J'ai aussi une perceuse Bosch GSB, achetée en 2023.",
                ],
            },
            evaluators=[
                entities_exist(names="marteau, perceuse"),
                prop_key_shared(entities="marteau, perceuse", pattern="achat|achet|date|annee"),
                same_entity_type(entities="marteau, perceuse"),
            ],
        ),
        EvalCase(
            name="wood_key_reuse_schema",
            inputs={
                "messages": ["J'ai aussi une perceuse Bosch GSB, achetée en 2023."],
                "seed": {
                    "entities": [
                        {"name": "marteau XP-55", "entity_type": "outil",
                         "props": {"date_achat": "2022"}},
                    ],
                },
            },
            evaluators=[
                entities_exist(names="perceuse"),
                has_prop_keys(entity="perceuse", keys="date_achat"),
                same_entity_type(entities="marteau, perceuse"),
            ],
        ),
        EvalCase(
            name="wood_relation",
            inputs={
                "messages": [
                    "La dalle béton fait 3 mètres sur 4. L'abri de jardin sera posé dessus.",
                ],
            },
            evaluators=[
                entities_exist(names="dalle, abri"),
                relation_between(a="abri", b="dalle"),
            ],
        ),
        # ───────── domaine 2 : polar ─────────
        EvalCase(
            name="noir_create",
            inputs={
                "messages": ["Marco Santi est le gérant du club Le Vesuvio, à Lyon."],
            },
            evaluators=[
                entities_exist(names="marco, vesuvio"),
                relation_between(a="marco", b="vesuvio"),
            ],
        ),
        EvalCase(
            name="noir_key_reuse_schema",
            inputs={
                "messages": [
                    "Léa Fontan est un témoin. Son alibi : elle était au cinéma le soir du 12 juin.",
                ],
                "seed": {
                    "entities": [
                        {"name": "Marco Santi", "entity_type": "personnage",
                         "props": {"role": "suspect", "alibi": "chez sa mère le soir du 12 juin"}},
                    ],
                },
            },
            evaluators=[
                entities_exist(names="lea"),
                has_prop_keys(entity="lea", keys="role, alibi"),
                same_entity_type(entities="marco, lea"),
            ],
        ),
        # ───────── domaine 3 : histoire (WW2) ─────────
        EvalCase(
            name="ww2_create",
            inputs={
                "messages": [
                    "Le pont de Remagen est capturé le 7 mars 1945 par la 9e division blindée américaine.",
                ],
            },
            evaluators=[
                entities_exist(names="remagen, 9e division"),
                relation_between(a="9e division", b="remagen"),
            ],
        ),
        EvalCase(
            name="ww2_key_reuse_schema",
            inputs={
                "messages": [
                    "Le pont Pegasus est capturé le 6 juin 1944 par la 6e division aéroportée britannique.",
                ],
                "seed": {
                    "entities": [
                        {"name": "pont de Remagen", "entity_type": "pont",
                         "props": {"date_capture": "7 mars 1945"}},
                    ],
                },
            },
            evaluators=[
                entities_exist(names="pegasus"),
                has_prop_keys(entity="pegasus", keys="date_capture"),
                same_entity_type(entities="remagen, pegasus"),
            ],
        ),
        # ───────── check de cohérence (voisinage + judge, zéro sémantique) ─────────
        EvalCase(
            name="check_direct_noir",
            inputs={
                "messages": ["Un témoin affirme avoir vu Marco au Vesuvio le soir du 12 juin."],
                # Le Vesuvio doit être localisé : sans adresse, « chez sa mère à
                # Marseille » vs « au Vesuvio » n'est pas une contradiction
                # démontrable — le judge l'a fait remarquer à juste titre.
                "seed": {
                    "entities": [
                        {"name": "Marco Santi", "entity_type": "personnage",
                         "props": {"alibi": "chez sa mère à Marseille le soir du 12 juin"}},
                        {"name": "Le Vesuvio", "entity_type": "lieu",
                         "props": {"adresse": "8 quai de Bondy, Lyon"}},
                    ],
                },
                "check": "marco",
            },
            evaluators=[check_verdict(expected=True)],
        ),
        EvalCase(
            name="check_relation_wood",
            inputs={
                "messages": ["L'abri de jardin fera 5 mètres de large."],
                "seed": atelier_seed_dalle,
                "check": "abri",
            },
            evaluators=[
                has_prop_keys(entity="abri", keys="largeur"),
                check_verdict(expected=True),
            ],
        ),
        EvalCase(
            name="check_no_false_positive",
            inputs={
                "messages": ["L'abri de jardin fera 2,5 mètres de large."],
                "seed": atelier_seed_dalle,
                "check": "abri",
            },
            evaluators=[
                has_prop_keys(entity="abri", keys="largeur"),
                check_verdict(expected=False),
            ],
        ),
        EvalCase(
            name="check_relation_ww2",
            inputs={
                "messages": [
                    "La 9e division blindée traverse le pont de Remagen le 15 mars 1945.",
                ],
                "seed": {
                    "entities": [
                        {"name": "pont de Remagen", "entity_type": "pont",
                         "props": {"effondrement": "10 mars 1945"}},
                        {"name": "9e division blindée", "entity_type": "unite_militaire", "props": {}},
                    ],
                },
                "check": "remagen",
            },
            evaluators=[check_verdict(expected=True)],
        ),
        # ───────── garde-fou ─────────
        EvalCase(
            name="no_write_question",
            inputs={"messages": ["Qu'est-ce que tu sais faire, exactement ?"]},
            evaluators=[no_entities],
        ),
        # ───────── échelle : needle in haystack ─────────
        EvalCase(
            name="scale_check_big_neighborhood",
            inputs={
                "messages": ["Un témoin formel a vu Marco au Vesuvio le soir du 12 juin."],
                "seed": big_noir_seed,
                "check": "marco",
            },
            evaluators=[check_verdict(expected=True)],
        ),
        EvalCase(
            name="scale_check_big_no_false_positive",
            inputs={
                "messages": ["Marco a déjeuné au Vesuvio avec Antoine Berger le 14 juin à midi."],
                "seed": big_noir_seed,
                "check": "marco",
            },
            evaluators=[check_verdict(expected=False)],
        ),
        # ───────── échelle : la bonne clé dans un schéma riche ─────────
        EvalCase(
            name="scale_schema_rich",
            inputs={
                "messages": [
                    "J'ai acheté une scie circulaire Makita 165 mm à 189 euros chez Brico Dépôt, le 3 mai 2024.",
                ],
                "seed": chantier_seed,
            },
            evaluators=[
                entities_exist(names="scie"),
                has_prop_keys(entity="scie", keys="prix, date_achat, fournisseur"),
                same_entity_type(entities="marteau, scie"),
            ],
        ),
        # ───────── échelle : conversation longue, références partielles, correction ─────────
        EvalCase(
            name="scale_long_conversation",
            inputs={
                "messages": [
                    "Marco Santi est le gérant du club Le Vesuvio, à Lyon.",
                    "Léa Fontan, une journaliste, enquête sur le Vesuvio.",
                    "Dans la nuit du 12 juin, un cambriolage a eu lieu au club.",
                    "L'alibi de Marco : il dit qu'il était chez sa mère cette nuit-là.",
                    "Léa a interviewé Marco le 14 juin.",
                    "Correction : l'alibi de Marco, c'est chez son frère, pas chez sa mère.",
                    "Santi possède aussi un bar à Villeurbanne, Le Goulot.",
                    "Récapitule : qui sont les personnages de mon histoire ?",
                ],
            },
            evaluators=[
                entities_exist(names="marco, lea, vesuvio, goulot"),
                count_matching(pattern="^marco|^santi", n=1),
                has_prop_value(entity="marco santi", key_pattern="alibi", value="frère"),
                relation_between(a="lea", b="marco santi"),
            ],
        ),
    ]
)
