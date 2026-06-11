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

from felix.core.graph import NARRATIVE_REL


def _or_types(types: tuple[str, ...]) -> str:
    """« personnage », « personnage ou groupe », « a, b ou c » — pour les messages guidants."""
    if not types:
        return "—"
    if len(types) == 1:
        return f"« {types[0]} »"
    return ", ".join(f"« {t} »" for t in types[:-1]) + f" ou « {types[-1]} »"


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
class RelationSpec:
    """Un type de relation canonique du domaine, AVEC son typage domaine/portée.

    ``subjects``/``objects`` listent les entity_types attendus aux deux extrémités.
    Le typage ORIENTE sans verrouiller : ``validate_relation`` ne refuse que les
    violations CLAIRES (extrémité d'un type connu du domaine mais hors-liste) ; un
    type inconnu (hors du vocabulaire de types du profil) passe — schemaless oblige,
    on ne sur-rejette pas les types que le modèle improvise.

    ``allow_self`` autorise une boucle (a == b) ; faux par défaut (un tract ne fait
    pas partie de lui-même).
    """

    name: str  # PRÉDICAT en CAPITALES anglaises (convention Neo4j, priors stables)
    gloss: str  # glose FR COURTE (rendue dans le prompt ET dans les messages d'enforcement)
    subjects: tuple[str, ...] = ()  # entity_types admis comme source
    objects: tuple[str, ...] = ()  # entity_types admis comme cible
    allow_self: bool = False
    # Exemples d'usage CONTRASTIFS (verbes du langage qui mappent vers ce type) —
    # rendus dans le prompt SEULEMENT (pas dans les messages d'enforcement, qu'on garde
    # courts). Combat l'attracteur « relation vague » : le petit modèle se rabat sur le
    # type le plus neutre faute de savoir lequel colle (cf. KNOWS). Few-shot > règle.
    examples: str = ""


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    entity_types: tuple[EntityType, ...]
    modeling_rules: tuple[str, ...] = ()
    consistency_rules: tuple[str, ...] = ()
    # Noyau STRUCTUREL fermé : les seuls types canoniques, typés (cf. RelationSpec) —
    # ceux que le code calcule ou affiche structurellement. L'anglais UPPER_SNAKE
    # (convention Neo4j) a des priors plus stables qu'une locution verbale FR → réduit
    # la dérive des noms de relations ; le typage domaine/portée coupe les relations
    # absurdes à l'écriture (cf. add_relation → validate_relation). Vide = aucune
    # contrainte (le profil ne gouverne pas les relations).
    relation_vocabulary: tuple[RelationSpec, ...] = ()
    # Canal NARRATIF (#68) : type générique unique dont le sens vit dans la prop
    # `verbe` (verbatim auteur). Sort du tapis roulant de l'énumération de types :
    # zéro trou par construction, zéro traduction (« maîtresse » ne devient plus
    # LOVES), zéro soupe (une paraphrase ne crée pas un type). "" = pas de canal
    # narratif (le hors-vocab garde la sortie légale seule, cf. validate_relation).
    narrative_rel: str = ""
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
            lines.append(
                "Relations STRUCTURELLES (réutilise ces types EXACTS, en CAPITALES "
                "anglaises) :"
            )
            for spec in self.relation_vocabulary:
                ex = f"  (ex. : {spec.examples})" if spec.examples else ""
                lines.append(f"- {spec.name} : {spec.gloss}{ex}")
        if self.narrative_rel:
            lines.append(
                f"TOUT AUTRE lien entre deux fiches (aimer, commander, surveiller, "
                f"faire chanter…) : add_relation avec rel_type={self.narrative_rel} "
                f"et verbe=« les mots EXACTS de l'auteur » (ex. verbe='était la "
                f"maîtresse de'). Ne traduis pas, ne résume pas : le verbe de "
                f"l'auteur EST la donnée."
            )
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
            lines.append("Types de relations STRUCTURELLES (CAPITALES anglaises, EXACTS) :")
            for spec in self.relation_vocabulary:
                ex = f"  (ex. : {spec.examples})" if spec.examples else ""
                lines.append(f"- {spec.name} : {spec.gloss}{ex}")
        if self.narrative_rel:
            lines.append(
                f"Tout AUTRE lien : rel_type={self.narrative_rel} + verbe=« les mots "
                f"exacts de l'auteur » (ex. verbe='était la maîtresse de')."
            )
        return "\n".join(lines)

    def render_check_rules(self) -> str:
        """Section du CHECK_PROMPT — vide si le profil n'a pas de règle de cohérence."""
        if not self.consistency_rules:
            return ""
        lines = [f"RÈGLES DE COHÉRENCE DU DOMAINE ({self.name}) :"]
        lines.extend(f"- {rule}" for rule in self.consistency_rules)
        return "\n".join(lines)

    @property
    def known_entity_types(self) -> frozenset[str]:
        """Vocabulaire de types « connus » du domaine — base du refus CLAIR : un type
        DANS cet ensemble mais hors-liste pour une relation = violation refusée ; un
        type HORS de cet ensemble (inventé par le modèle) = toléré. Réunit les types
        déclarés, ceux cités dans le typage des relations, et 'evenement' si géré."""
        types = {et.name for et in self.entity_types}
        for spec in self.relation_vocabulary:
            types.update(spec.subjects)
            types.update(spec.objects)
        if self.manages_events:
            types.add("evenement")
        return frozenset(types)

    def validate_relation(  # noqa: PLR0911 — chaque refus est un message GUIDANT distinct
        self, rel_type: str, subject_type: str, object_type: str, *, same_node: bool,
        verbe: str = "",
    ) -> str | None:
        """Valide une relation à l'écriture. Retourne ``None`` si OK, sinon un message
        GUIDANT (refus, renvoyé tel quel à l'agent — pas une exception, donc pas de
        boucle ModelRetry). Règles, dans l'ordre :

        1. canal NARRATIF (rel_type == narrative_rel) : verbe verbatim REQUIS, pas
           de boucle a==b ; AUCUNE validation domaine/portée — le verbe fidèle de
           l'auteur prime sur un typage qu'on ne peut pas énumérer (#68) ;
        2. type ∈ vocabulaire structurel (sinon refus, orienté vers le canal
           narratif s'il existe) — sauf profil sans vocab (tout permis) ;
        3. pas de boucle a==b si ``allow_self`` est faux ;
        4. domaine/portée : sujet/objet d'un type CONNU mais hors-liste → refus ;
           type inconnu → toléré (schemaless).
        """
        if self.narrative_rel and rel_type == self.narrative_rel:
            if not verbe.strip():
                return (
                    f"Une relation {self.narrative_rel} porte son sens dans son "
                    f"verbe : rappelle add_relation avec verbe=« les mots exacts "
                    f"de l'auteur » (ex. verbe='était la maîtresse de')."
                )
            if same_node:
                return "Une relation ne peut pas relier une entité à elle-même."
            return None

        if not self.relation_vocabulary:
            return None  # profil ne gouverne pas les relations → tout permis

        spec = next((s for s in self.relation_vocabulary if s.name == rel_type), None)
        if spec is None:
            allowed = ", ".join(s.name for s in self.relation_vocabulary)
            if self.narrative_rel:
                # Plus de trou de vocab : le canal narratif est la sortie (#68).
                # On garde le droit de se taire si le texte ne pose pas le lien.
                return (
                    f"« {rel_type} » n'est pas un type du domaine « {self.name} ». "
                    f"Types STRUCTURELS exacts : {allowed}. Pour tout AUTRE lien "
                    f"réel du texte, utilise rel_type={self.narrative_rel} avec "
                    f"verbe=« les mots exacts de l'auteur ». Si le texte ne pose "
                    f"pas ce lien, n'écris rien."
                )
            # Sortie LÉGALE au trou de vocab : sans elle, le modèle se rabat sur
            # le type « le plus proche » et fabrique du canon faux avec assurance
            # (« Lancelot WITNESSES dépression », #64). Mieux vaut zéro arête.
            return (
                f"« {rel_type} » n'est pas une relation du domaine « {self.name} ». "
                f"Utilise l'un de ces types EXACTS : {allowed}. Si AUCUN ne "
                f"correspond au lien réel, n'écris PAS de relation : cette "
                f"information est une propriété de fiche, pas une arête."
            )

        if same_node and not spec.allow_self:
            return f"Une relation « {rel_type} » ne peut pas relier une entité à elle-même."

        known = self.known_entity_types
        if subject_type in known and subject_type not in spec.subjects:
            return (
                f"Le sujet d'une relation « {rel_type} » ({spec.gloss}) devrait être de "
                f"type {_or_types(spec.subjects)}, pas « {subject_type} »."
            )
        if object_type in known and object_type not in spec.objects:
            return (
                f"La cible d'une relation « {rel_type} » ({spec.gloss}) devrait être de "
                f"type {_or_types(spec.objects)}, pas « {object_type} »."
            )
        return None


# ─────────────────────────── profil scénario v0 ───────────────────────────
# Un seul profil câblé en dur pour l'instant (pas de sélecteur de domaine).
# Pas de notion d'ère : era meurt avec le nouveau monde :GenEntity.
SCENARIO_PROFILE = Profile(
    name="scénario",
    description="Tu tiens la « bible » d'une fiction : ses personnages, lieux, "
    "événements et objets.",
    entity_types=(
        EntityType(
            "personnage", ("background", "age", "traits", "alibi"),
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
        EntityType(
            "groupe", ("description", "camp"),
            "Une faction, une organisation, une armée (ex. le FLN). Un personnage en "
            "est MEMBER_OF ; ne crée PAS un groupe comme un personnage.",
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
        "Ce qu'un personnage FAIT ou ressent dans un beat (« sourit », « rouge de "
        "colère », « serre le tract », « avale une pilule », « ferme les yeux ») est "
        "une ACTION → un ÉVÉNEMENT, et n'enrichit AUCUNE propriété. En particulier "
        "n'ALLONGE JAMAIS `traits` avec une action : `traits` ne porte que le DURABLE "
        "(« colonial pur suif », « cheveux gris », « parle arabe couramment »). Sa "
        "trajectoire se lit dans la chronologie, pas dans une prop (« arc », "
        "« situation »…). Si le beat ne t'apprend aucun fait durable NOUVEAU sur un "
        "personnage existant, ne le mets PAS à jour.",
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
    # Noyau STRUCTUREL fermé (#68) : les seuls types dont le sens est calculé ou
    # affiché structurellement par le code (machinerie events + topologie). Le
    # typage coupe à l'écriture les relations absurdes vues sur « Alger 1957 »
    # (LOCATED_AT→objet, boucle PART_OF…). 'evenement' n'apparaît jamais via
    # add_relation (find_non_event l'exclut), mais reste listé pour la cohérence
    # conceptuelle du domaine. Le narratif (aimer, commander, surveiller…) ne
    # s'énumère pas : il passe par narrative_rel + verbe verbatim — l'historique
    # complet du tapis roulant (soupe d'Alger → vocab dur → trous infinis) est
    # dans l'issue #68.
    relation_vocabulary=(
        RelationSpec("LOCATED_AT", "se trouve / se déroule dans un lieu",
                     subjects=("personnage", "objet", "evenement", "groupe"),
                     objects=("lieu",),
                     examples="est à, vit à, se trouve dans, se déroule à, "
                              "le groupe vit à"),
        RelationSpec("MEMBER_OF", "appartient à un groupe / une organisation",
                     subjects=("personnage",), objects=("groupe",),
                     examples="est membre du FLN, appartient à la police, est dans le gang"),
        RelationSpec("PART_OF", "fait partie d'un ensemble plus grand",
                     subjects=("lieu", "objet", "groupe"), objects=("lieu", "objet", "groupe"),
                     examples="la cave fait partie de l'école, une aile d'un bâtiment"),
    ),
    narrative_rel=NARRATIVE_REL,
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
