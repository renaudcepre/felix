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
        return "\n".join(lines)

    def render_schema_hint(self) -> str:
        """Réponse de describe_schema sur base vide : oriente sans verrouiller."""
        lines = [
            f"Base vide. Pour ce domaine ({self.name}), utilise de préférence ces "
            "types et noms de propriétés (tu peux t'en écarter si le sens l'exige) :"
        ]
        for et in self.entity_types:
            lines.append(f"- {et.name} · propriétés usuelles : {', '.join(et.keys)}")
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
            "evenement", ("date", "lieu", "resume"),
            "Un événement se DATE : pose sa date en propriété.",
        ),
        EntityType(
            "objet", ("description", "proprietaire"),
            "Une arme, un indice, un objet de l'intrigue.",
        ),
    ),
    modeling_rules=(
        "Une caractéristique d'une chose (âge, couleur, rôle…) est une PROPRIÉTÉ, "
        "jamais une entité séparée.",
        "Quand deux personnages interagissent, crée la relation qui les lie.",
    ),
    consistency_rules=(
        "Un personnage mort ne peut plus agir ni apparaître après sa mort "
        "(la mort est un état terminal).",
        "Un même personnage ne peut pas être à deux lieux incompatibles au même moment.",
        "Deux dates ou deux lieux donnés pour un même fait doivent être compatibles.",
    ),
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
