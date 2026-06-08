"""Profil de domaine — données déclaratives qui ORIENTENT (sans contraindre) le
noyau schemaless vers un domaine donné.

v0 : pure-données Python (``frozen=True``). Structuré pour devenir un fichier
éditable à la couche « auto-apprenante » plus tard — pas de YAML pour l'instant.

Le profil transite par deux canaux :
- ``deps.profile`` : lu par les tools (describe_schema sur base vide) ;
- ``create_core_agent(profile)`` / ``consistency_check(profile=...)`` : concaténé
  au system prompt et au prompt du check.

Trois rendus, un par point d'injection :
- ``render_prompt_block``  → bloc « === DOMAINE === » du system prompt (court) ;
- ``render_schema_hint``   → réponse de describe_schema quand la base est vide ;
- ``render_check_rules``   → section « RÈGLES DE COHÉRENCE DU DOMAINE » du check.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntityType:
    """Un type d'entité recommandé pour le domaine, avec ses clés usuelles.

    ``note`` rappelle un piège de modélisation propre au type (ex. « un alibi est
    une PROPRIÉTÉ, pas une entité »).
    """

    name: str
    keys: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    entity_types: tuple[EntityType, ...]
    modeling_rules: tuple[str, ...] = ()
    consistency_rules: tuple[str, ...] = ()
    # Types de relation canoniques : (PRÉDICAT en CAPITALES anglaises, glose FR).
    # L'anglais UPPER_SNAKE (convention Neo4j) a des priors plus stables qu'une
    # locution verbale FR → réduit la dérive des noms de relations.
    relation_vocabulary: tuple[tuple[str, str], ...] = ()
    # Le domaine réserve le type 'evenement' au mécanisme add_event (ordre/NEXT) :
    # add_entity refuse alors d'en créer un comme entité plate (sinon node hors
    # chaîne, hors chronologie). False = domaine sans chronologie dédiée.
    manages_events: bool = False

    def render_prompt_block(self) -> str:
        """Bloc concaténé au system prompt — volontairement compact (petit modèle)."""
        lines = [f"=== DOMAINE : {self.name} ===", self.description,
                 "Types d'entités usuels (réutilise-les quand le sens correspond) :"]
        for et in self.entity_types:
            note = f" — {et.note}" if et.note else ""
            lines.append(f"- {et.name} : {', '.join(et.keys)}{note}")
        if self.modeling_rules:
            lines.append("Modélisation :")
            lines.extend(f"- {rule}" for rule in self.modeling_rules)
        if self.relation_vocabulary:
            lines.append("Relations (réutilise ces types EXACTS, en CAPITALES anglaises) :")
            lines.extend(f"- {pred} : {gloss}" for pred, gloss in self.relation_vocabulary)
        return "\n".join(lines)

    def render_schema_hint(self) -> str:
        """Réponse de describe_schema sur base vide : oriente sans verrouiller."""
        lines = [
            f"Base vide. Pour ce domaine ({self.name}), utilise de préférence ces "
            "types et noms de propriétés (tu peux t'en écarter si le sens l'exige) :"
        ]
        for et in self.entity_types:
            lines.append(f"- {et.name} · propriétés usuelles : {', '.join(et.keys)}")
        if self.relation_vocabulary:
            lines.append("Types de relations à réutiliser (CAPITALES anglaises) :")
            lines.extend(f"- {pred} : {gloss}" for pred, gloss in self.relation_vocabulary)
        return "\n".join(lines)

    def render_check_rules(self) -> str:
        """Section du CHECK_PROMPT — vide si le profil n'a pas de règle de cohérence."""
        if not self.consistency_rules:
            return ""
        lines = [f"RÈGLES DE COHÉRENCE DU DOMAINE ({self.name}) :"]
        lines.extend(f"- {rule}" for rule in self.consistency_rules)
        return "\n".join(lines)


# ─────────────────────────── profil scénario v0 ───────────────────────────
# Un seul profil câblé en dur pour l'instant (pas de sélecteur de domaine).
# Pas de notion d'ère : era meurt avec le nouveau monde :GenEntity.
SCENARIO_PROFILE = Profile(
    name="scénario",
    description="Tu tiens la « bible » d'une fiction : ses personnages, lieux, "
    "événements et objets.",
    entity_types=(
        EntityType(
            "personnage", ("background", "age", "traits", "arc", "alibi"),
            "Un alibi, un trait ou un âge est une PROPRIÉTÉ du personnage, pas une entité.",
        ),
        EntityType(
            "lieu", ("description", "ambiance"),
            "Une ville, un bâtiment, une pièce sont des lieux.",
        ),
        EntityType(
            "objet", ("description", "proprietaire"),
            "Une arme, un indice, un objet de l'intrigue.",
        ),
    ),
    modeling_rules=(
        "Une caractéristique d'une chose (âge, couleur, rôle…) est une PROPRIÉTÉ, "
        "jamais une entité séparée.",
        "Une ACTION qui se passe à un instant — qu'on la nomme par un verbe "
        "(« tire », « verrouille », « sauve ») ou par un nom (« le sabotage », "
        "« le piégeage ») — n'est NI une propriété NI une entité : c'est un "
        "ÉVÉNEMENT, tenu à part dans la chronologie. Ne la range pas dans une prop "
        "(elle serait écrasée au geste suivant) et n'en fais pas une entité. Une "
        "propriété décrit ce qu'un personnage EST durablement (background, âge, "
        "traits, rôle, vivant/mort).",
        "Quand deux personnages interagissent, crée la relation qui les lie.",
        "Un fait qui DIVERGE d'une valeur déjà posée se range sous une NOUVELLE "
        "clé, on n'écrase pas. Ex. : alibi='chez sa mère à Marseille' existe ; "
        "« un témoin l'a vu au Vesuvio à Lyon » → garde alibi ET ajoute "
        "alibi_temoin='au Vesuvio à Lyon le 12' (deux propriétés, pas une). "
        "On n'écrase alibi que si l'auteur corrige explicitement.",
    ),
    consistency_rules=(
        "Un personnage ne peut plus AGIR de lui-même (parler, frapper, se "
        "déplacer…) après l'ÉVÉNEMENT de sa mort ; il peut en revanche rester "
        "sujet passif (on retrouve son corps, on l'enterre, on le venge) — ce "
        "n'est pas une contradiction. Seul l'agir d'ordre postérieur à la mort l'est.",
        "Un même personnage ne peut pas être à deux lieux incompatibles au même moment.",
        "Deux dates ou deux lieux donnés pour un même fait doivent être compatibles.",
    ),
    relation_vocabulary=(
        ("LOCATED_AT", "se trouve / se déroule dans un lieu"),
        ("MEMBER_OF", "appartient à une faction, un groupe, une organisation"),
        ("OWNS", "possède un objet"),
        ("KNOWS", "connaît / est lié à un personnage (lien neutre)"),
        ("ALLIED_WITH", "est allié de / aide un personnage ou un groupe"),
        ("FIGHTS", "affronte / combat"),
        ("KILLS", "tue ou détruit"),
        ("CREATES", "crée, fabrique, forge"),
        ("TARGETS", "vise, traque, prend pour cible ou pour victime"),
        ("CAUSES", "provoque un événement ou un état"),
        ("PART_OF", "fait partie d'un ensemble plus grand"),
        ("WITNESSES", "découvre, observe, examine"),
    ),
    manages_events=True,
)


# Second domaine concret (gestion de travaux) — démontre que le « scénario »
# n'est qu'un profil parmi d'autres posés sur le même noyau.
CHANTIER_PROFILE = Profile(
    name="chantier",
    description="Tu tiens le suivi d'un chantier : outils, matériaux, ouvrages "
    "et intervenants.",
    entity_types=(
        EntityType(
            "outil", ("date_achat", "prix", "fournisseur", "etat"),
            "Une perceuse, un marteau ; prix et date sont des propriétés.",
        ),
        EntityType(
            "materiau", ("essence", "quantite", "prix", "fournisseur"),
            "Du bois, des panneaux ; la quantité est une propriété.",
        ),
        EntityType(
            "ouvrage", ("largeur", "longueur", "hauteur", "date"),
            "Une dalle, un abri ; ses dimensions sont des propriétés.",
        ),
        EntityType(
            "intervenant", ("role", "tarif_jour", "telephone"),
            "Un maçon, un client ; son métier est une propriété 'role'.",
        ),
    ),
    modeling_rules=(
        "Un prix, une date, une dimension sont des PROPRIÉTÉS, pas des entités.",
        "Quand un ouvrage repose sur un autre ou qu'un matériau vient d'un "
        "fournisseur, crée la relation.",
    ),
    consistency_rules=(
        "Un ouvrage posé sur un autre ne peut pas être plus grand que son support.",
        "Les dates (achat, coulage, livraison) doivent être cohérentes entre elles.",
        "Une quantité ou un prix ne peut pas être négatif.",
    ),
)
