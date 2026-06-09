"""Agent du bot B — copilote d'écriture (atelier), assemblé sur le noyau générique.

Sélecteur de profil : l'atelier peut tourner sur le profil scénario, le profil
chantier, ou le NOYAU NU (aucun profil) pour tester le schéma émergent sans
instruction de domaine. Tous gardent les 5 tools du noyau + list_entities, et la
discipline schemaless (SYSTEM_PROMPT) qui est le moteur, pas une instruction de
domaine. create_atelier_agent() conserve sa signature (défaut = scénario).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from felix.core import CHANTIER_PROFILE, SCENARIO_PROFILE, create_core_agent
from felix.core.agent import CHRONICLE_SYSTEM_PROMPT, RELATION_SYSTEM_PROMPT
from felix.core.tools import (
    add_entity,
    add_event,
    add_relation,
    describe_schema,
    find_entity,
    list_entities,
    noter_le_passage,
)

# Outils du relieur (passe 2) : le noyau SANS update_entity. Sa tâche est de RELIER
# (add_relation), pas de toucher aux propriétés — le churn de props (ex. `arc`
# réécrit à chaque beat) venait en partie de re-updates ici, par-dessus la passe 1.
# Il garde add_entity en BACKFILL (relier une entité ratée par la 1re passe sans
# boucler sur un outil manquant — le piège du relieur trop restreint).
RELATION_TOOLS = (describe_schema, find_entity, add_entity, add_relation)

# Outils du MAÎTRE (chef d'orchestre, passe 0) : LECTURE SEULE de la bible +
# l'outil-signal. Aucun outil d'écriture → il ne PEUT pas inventer d'entité (l'hallu
# « salut → invente » devient impossible par construction). Il MÈNE la conversation
# et, s'il y a du contenu, appelle noter_le_passage → la route dispatche les extracteurs.
MASTER_TOOLS = (find_entity, list_entities, noter_le_passage)

if TYPE_CHECKING:
    from pydantic_ai import Agent

    from felix.core import GenericDeps, Profile

ATELIER_PERSONA = """\
Tu es Felix, copilote d'écriture de scénario. Tu accompagnes l'auteur pendant
qu'il raconte son histoire et tu tiens à jour sa « bible » (les fiches de son
univers) au fil de la parole. Ton chaleureux et sobre. NE RÉCAPITULE PAS ce que
tu enregistres (« j'ai noté X, Y, Z ») : les fiches s'affichent d'elles-mêmes à
côté, et annoncer une écriture que tu ne fais pas serait trompeur. Réagis plutôt à
l'HISTOIRE en une phrase, puis relance avec UNE seule question utile à l'écriture.
Pour répondre à une question sur le contenu de la bible (qui existe, ce qu'on
sait de quelqu'un), consulte-la d'abord (list_entities, find_entity) — ne devine
jamais.
"""

CHANTIER_PERSONA = """\
Tu es Felix, assistant de suivi de chantier. Tu tiens à jour l'inventaire et
l'avancement (outils, matériaux, ouvrages, intervenants) au fil de la discussion.
Ton clair et concret. Après une écriture, confirme en une phrase et propose UNE
relance utile. Pour répondre à une question sur le contenu, consulte-le d'abord
(list_entities, find_entity) — ne devine jamais.
"""

# Noyau nu : aucune instruction de domaine, juste de quoi rester utilisable
# (confirmer, relire). Sert à tester si la structure émerge sans profil.
NEUTRAL_PERSONA = """\
Tu tiens une base de connaissances structurée au fil de la conversation. Confirme
brièvement chaque écriture. Pour répondre à une question sur le contenu de la
base, consulte-le d'abord (list_entities, find_entity) — ne devine jamais.
"""

# ─────────── MAÎTRE (passe 0) : mène la conversation ET route l'extraction ───────────
MASTER_PERSONA = """\
Tu es Felix, copilote d'écriture de scénario. Tu MÈNES la conversation avec
l'auteur pendant qu'il raconte son histoire : ton chaleureux et sobre, tu réagis à
l'HISTOIRE en une phrase, puis tu relances avec UNE seule question utile à
l'écriture. Tu ne récapitules pas ce qui est enregistré (les fiches s'affichent
d'elles-mêmes à côté).
"""

# Le maître ne fait PAS d'extraction : il décide s'il FAUT en faire. Discipline de
# routage + few-shot (cf. [[feedback_prompt_engineering]] : few-shot > règles
# abstraites pour les petits modèles), formulée en POSITIF.
MASTER_SYSTEM_PROMPT = """\
Tu diriges une conversation d'écriture. Tu ne touches JAMAIS à la base toi-même :
tu peux seulement la LIRE (find_entity, list_entities) et SIGNALER quand il y a du
contenu à y enregistrer (noter_le_passage).

À chaque message :
1. Réponds à l'auteur — 1 à 2 phrases, puis UNE question utile à l'écriture.
2. Décide s'il y a du CONTENU À ENREGISTRER. La règle est simple :
   - Le message AFFIRME un fait sur le monde — un personnage / lieu / objet (même
     juste nommé), un lien entre eux (« a un homme de main », « surveille »,
     « possède »), une action qui se passe, ou une CORRECTION d'un fait existant ?
     → c'est du CONTENU, MÊME en une phrase brève : appelle noter_le_passage(resume).
   - Sinon (salutation, remerciement, bavardage, hésitation sans fait, ou une
     QUESTION/demande de rappel) → n'appelle RIEN.

La distinction clé : une AFFIRMATION qui pose un fait = contenu (on note) ; une
QUESTION ou une demande, même si elle nomme des entités, n'est PAS du contenu (lire
n'est pas écrire). Pour une question (« qui est X ? », « qu'a-t-on sur Y ? »),
consulte la bible (find_entity / list_entities) — ne devine jamais — et n'appelle
PAS noter_le_passage. Dans le doute, si le message APPORTE un fait, note-le.

Exemples :
- « salut » / « ça va ? » / « merci, c'est cool » → réponds, n'appelle RIEN.
- « je sais pas trop par où commencer » → relance, n'appelle RIEN (aucun fait).
- « qui est Nora, déjà ? » → find_entity('Nora'), réponds, n'appelle RIEN.
- « Nora débarque à Port-Vendres pour enquêter sur le maire Castan » →
  noter_le_passage("arrivée de Nora à Port-Vendres ; enquête sur le maire Castan").
- « le maire a un garde du corps, Tomas » (affirmation brève qui introduit une
  entité + un lien) → noter_le_passage("Tomas, garde du corps du maire").
- « le soir, dans la ruelle, Tomas file le journaliste » (action concrète) →
  noter_le_passage("Tomas file le journaliste, le soir dans la ruelle").
- « en fait Joseph ne déteste pas Castan : son fils est mort dans un accident » →
  noter_le_passage("correction du mobile de Joseph : la mort de son fils").

Réponds en français, 2 phrases maximum.
"""


# Passe 2 dédiée : le « relieur ». Décompose l'extraction (entités d'abord, puis
# relations) — un sous-agent à un seul job rate moins ses relations qu'un gros
# tour qui jongle avec tout (cf. sous-extraction mesurée en mono-passe).
RELATION_PERSONA = """\
Tu es le relieur du graphe. Les entités de ce passage existent DÉJÀ dans la base
(consulte-les avec list_entities / describe_schema). Ta SEULE tâche : créer les
relations qui les lient pour ce passage, avec add_relation, en réutilisant les
types de relation canoniques du domaine (CAPITALES anglaises). N'ajoute, ne
modifie, ne supprime AUCUNE entité ; si une entité te semble manquante, ignore-la.
Procède relation par relation, puis confirme en une phrase.
"""

# Passe 3 dédiée : le « chroniqueur ». Transforme le passage en ÉVÉNEMENTS ordonnés
# (état vs événement) — un beat d'action ne doit plus s'écraser dans une prop. Job
# unique = add_event ; l'ordre/NEXT/INVOLVES sont gérés en code par le tool.
CHRONICLE_PERSONA = """\
Tu es le chroniqueur du récit. Les entités de ce passage existent DÉJÀ dans la base
(consulte-les avec list_entities). Ta SEULE tâche : repérer les 1 à 3 actions-clés
qui SE PASSENT dans ce passage et les enregistrer avec add_event, en y reliant les
participants existants. Tu ne touches à rien d'autre ; un état durable n'est pas un
événement et ne te concerne pas.
"""


@dataclass(frozen=True)
class AgentChoice:
    key: str
    label: str
    profile: Profile | None
    persona: str


# Registre des modes proposés par le sélecteur de l'UI.
ATELIER_CHOICES: dict[str, AgentChoice] = {
    "scenario": AgentChoice("scenario", "Scénario", SCENARIO_PROFILE, ATELIER_PERSONA),
    "chantier": AgentChoice("chantier", "Chantier", CHANTIER_PROFILE, CHANTIER_PERSONA),
    "none": AgentChoice("none", "Aucun (noyau nu)", None, NEUTRAL_PERSONA),
}
DEFAULT_PROFILE = "scenario"


def build_atelier_agent(choice: AgentChoice) -> Agent[GenericDeps, str]:
    """Noyau (5 tools) + list_entities (énumération de la bible), pour un profil donné."""
    agent = create_core_agent(profile=choice.profile, persona=choice.persona)
    agent.tool(list_entities)
    return agent


def create_atelier_agent(profile_key: str = DEFAULT_PROFILE) -> Agent[GenericDeps, str]:
    return build_atelier_agent(ATELIER_CHOICES[profile_key])


def build_master_agent(choice: AgentChoice) -> Agent[GenericDeps, str]:
    """Passe 0 « maître » : MÈNE la conversation (texte streamé) et ROUTE l'extraction.

    Outils en LECTURE SEULE (find_entity, list_entities) + l'outil-signal
    noter_le_passage : aucun outil d'écriture → il ne PEUT pas inventer d'entité.
    La route ne lance les extracteurs (entités/relieur/chroniqueur) + le juge que
    s'il a appelé noter_le_passage — un bavardage/une question n'écrit donc RIEN."""
    return create_core_agent(
        profile=choice.profile,
        persona=MASTER_PERSONA,
        system_prompt=MASTER_SYSTEM_PROMPT,
        tools=MASTER_TOOLS,
    )


def create_master_agent(profile_key: str = DEFAULT_PROFILE) -> Agent[GenericDeps, str]:
    return build_master_agent(ATELIER_CHOICES[profile_key])


def build_relation_agent(choice: AgentChoice) -> Agent[GenericDeps, str]:
    """2e passe « relieur » : outils RESTREINTS (RELATION_TOOLS = noyau sans
    update_entity) + discipline/persona qui priorisent add_relation. Sans
    update_entity, il ne PEUT plus re-toucher les props (fin du churn) ; il garde
    add_entity en filet (backfill d'une entité ratée par la 1re passe)."""
    agent = create_core_agent(
        profile=choice.profile,
        persona=RELATION_PERSONA,
        system_prompt=RELATION_SYSTEM_PROMPT,
        tools=RELATION_TOOLS,
    )
    agent.tool(list_entities)
    return agent


def create_relation_agent(profile_key: str = DEFAULT_PROFILE) -> Agent[GenericDeps, str]:
    return build_relation_agent(ATELIER_CHOICES[profile_key])


def build_chronicle_agent(choice: AgentChoice) -> Agent[GenericDeps, str]:
    """3e passe « chroniqueur » : transforme le beat en événements ordonnés. Outils
    RESTREINTS (lecture + add_event) — add_event absorbe les participants manquants,
    donc pas de boucle sur outil absent (contrairement au piège du relieur restreint
    qui réclamait add_entity)."""
    agent = create_core_agent(
        profile=choice.profile,
        persona=CHRONICLE_PERSONA,
        system_prompt=CHRONICLE_SYSTEM_PROMPT,
        tools=(describe_schema, find_entity, add_event),
    )
    agent.tool(list_entities)
    return agent


def create_chronicle_agent(profile_key: str = DEFAULT_PROFILE) -> Agent[GenericDeps, str]:
    return build_chronicle_agent(ATELIER_CHOICES[profile_key])
