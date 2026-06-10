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

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.core import CHANTIER_PROFILE, SCENARIO_PROFILE, create_core_agent
from felix.core.agent import CHRONICLE_SYSTEM_PROMPT, RELATION_SYSTEM_PROMPT
from felix.core.tools import (
    add_entity,
    add_event,
    add_relation,
    describe_schema,
    find_entity,
    list_entities,
)
from felix.llm import build_chat_model

# Outils du relieur (passe 2) : le noyau SANS update_entity. Sa tâche est de RELIER
# (add_relation), pas de toucher aux propriétés — le churn de props (ex. `arc`
# réécrit à chaque beat) venait en partie de re-updates ici, par-dessus la passe 1.
# Il garde add_entity en BACKFILL (relier une entité ratée par la 1re passe sans
# boucler sur un outil manquant — le piège du relieur trop restreint).
RELATION_TOOLS = (describe_schema, find_entity, add_entity, add_relation)

# Outils du MAÎTRE (chef d'orchestre, passe 0) : LECTURE SEULE de la bible. Aucun
# outil d'écriture → il ne PEUT pas inventer d'entité (l'hallu « salut → invente »
# devient impossible par construction). Il MÈNE la conversation ; la DÉCISION
# d'extraire ne lui appartient plus : elle est portée par le GATE stateless
# (build_gate_agent), hors du fil threadé.
MASTER_TOOLS = (find_entity, list_entities)

if TYPE_CHECKING:
    from pydantic_ai.models import Model

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

# ─────────── MAÎTRE (passe 0) : BLOC-NOTES, pas interviewer ───────────
# Retour utilisateur (2026-06-10) : « relance avec UNE question » à chaque tour est
# insupportable — l'auteur veut un BLOC-NOTES qui écoute et RÉAGIT, pas un coach qui
# mène l'entretien. Le même réflexe « avoir l'air engagé » faisait aussi CONFABULER
# du concret sur base vide. A/B de persona mesuré : interviewer 12/12 relance vs
# bloc-notes 0/12 relance + 0 confabulation (voix « réagit sobrement, jamais de
# question » choisie par l'utilisateur). Cf. [[project_master_blocnotes]], JOURNAL
# « Maître → bloc-notes », harness `just ab-blocnotes`.
MASTER_PERSONA = """\
Tu es Felix, le bloc-notes vivant de l'auteur. Il déroule son histoire ; tu
l'accompagnes en retrait. À chaque tour, tu RÉAGIS en une phrase courte et sincère
à ce qu'il vient de dire — sans jamais ajouter un détail qu'il n'a pas donné — puis
tu t'arrêtes. Tu ne le questionnes pas, tu ne le diriges pas : tu reçois.
"""

# Le maître ne décide PLUS de l'extraction (cf. GATE ci-dessous) et n'écrit JAMAIS
# (lecture seule). En mode bloc-notes, la discipline : réagir brièvement à l'HISTOIRE,
# ne pas questionner, ne rien inventer, ne pas annoncer l'enregistrement, ne pas
# deviner la bible.
MASTER_SYSTEM_PROMPT = """\
Tu es un bloc-notes d'écriture, pas un interlocuteur qui mène l'entretien.
L'auteur déroule son histoire ; tu la reçois.

- RÉAGIS en UNE phrase courte à ce qu'il vient de dire — un mot d'intérêt sincère
  sur l'HISTOIRE elle-même, accroché à ce qu'elle a de CONCRET. Évite les mots
  passe-partout (« intéressant », « pas mal »). Puis tu t'arrêtes.
- Ne pose PAS de question. Tu ne relances pas, tu ne demandes ni « et ensuite »,
  ni « pourquoi », ni « comment ». (Seule exception : si l'auteur cale ou te le
  demande explicitement — alors une seule, sobre.)
- N'INVENTE jamais un détail qu'il n'a pas donné : pas de portrait, pas de décor,
  pas de passé brodé. Tu réagis à ce qui est dit, tu n'ajoutes aucun fait.
- Ne dis pas « noté » / « j'enregistre » / « c'est noté » : les fiches s'affichent
  d'elles-mêmes à côté. Réagis à l'HISTOIRE, pas à l'acte d'enregistrer.
- Pour une question sur ce qui existe déjà, consulte la bible (find_entity /
  list_entities) — ne devine jamais.

Réponds en français, une phrase, très bref.
"""


# ─────────── GATE de routage (stateless) : décide s'il faut extraire ───────────
class RouteDecision(BaseModel):
    """Sortie structurée du gate — `fait` AVANT `noter` (reason-first : le modèle
    formule le fait, puis tranche ; l'inverse fait trancher Small à l'aveugle)."""

    fait: str = Field(
        description="le fait que le message apporte sur l'histoire, en une phrase ; "
        "chaîne vide s'il n'y en a aucun"
    )
    noter: bool = Field(
        description="vrai s'il y a du contenu à enregistrer dans la bible"
    )


# La décision d'extraire est STATELESS : le gate ne voit QUE le message du tour,
# jamais le fil ni ses décisions passées — l'ornière d'auto-imitation (un tour 1
# mal classé imité toute la session, dogfood 2026-06-10, issue #43) devient
# impossible par construction. Règle « hedge + contenu = contenu » : l'hésitation
# ne compte pas, seul compte le fait. Few-shot univers prompt-only Sel/Mirko/
# Vellone (cf. [[feedback_prompt_test_leakage]]).
GATE_SYSTEM_PROMPT = """\
Tu es le filtre d'enregistrement d'un copilote d'écriture de scénario. On te donne
UN message de l'auteur, seul, hors contexte. Décide s'il apporte du CONTENU à
enregistrer dans la bible de son histoire (personnages, lieux, objets, groupes,
relations, événements).

NOTER (noter=true) si le message AFFIRME ou ESQUISSE un fait sur le monde de
l'histoire :
- un personnage / lieu / objet / groupe, même juste mentionné ou proposé ;
- un NOM donné à une entité (« X se nomme Y », « on va l'appeler Z ») ;
- un lien entre entités (« a un homme de main », « surveille ») ;
- une action qui se passe, ou une CORRECTION d'un fait existant.
L'HÉSITATION NE COMPTE PAS : ignore les marqueurs de doute (« je sais pas trop »,
« peut-être », « un truc genre », le conditionnel, le « ? » d'une idée proposée).
Une fois le doute retiré, s'il reste un fait ou une ébauche d'histoire → noter=true.

NE PAS NOTER (noter=false) si le message ne pose AUCUN fait : salutation,
remerciement, réaction (« ouais », « pas mal »), pur « je sais pas par où
commencer », ou une QUESTION sur ce qui existe déjà (« qui est X ? »,
« résume-moi ce qu'on a ») — lire n'est pas écrire.

Exemples (un univers d'illustration — la règle vaut pour toute histoire) :
- « salut » / « merci, c'est top » / « ouais, pas mal » → noter=false, fait="".
- « je sais pas trop par où commencer » → noter=false, fait="" (aucun fait).
- « qui est Mirko, déjà ? » → noter=false, fait="" (question : lire n'est pas écrire).
- « Sel, une cartographe, arrive à Vellone pour lever les plans des galeries
  interdites » → noter=true, fait="Sel, cartographe, arrive à Vellone relever les
  galeries interdites".
- « hmm, peut-être un truc où l'intendant aurait perdu un fils, autrefois ? » →
  noter=true, fait="l'intendant a perdu un fils autrefois" (hésitation MAIS une
  ébauche d'histoire : on note le fait, pas le doute).
- « le contremaître se nomme "Drass" » → noter=true, fait="le contremaître
  s'appelle Drass".
- « en fait l'éboulement n'était pas un accident : la poutre a été sciée » →
  noter=true, fait="correction : l'éboulement est un sabotage de la poutre".
"""


def build_gate_agent() -> Agent[None, RouteDecision]:
    """Gate de routage : un appel court, SANS outils ni deps, sortie structurée.

    Appelé par la route avec le message du tour SEUL (jamais d'historique) : la
    fraîcheur de la décision est la propriété qui tue l'ornière — ne pas lui
    passer de message_history."""
    return Agent(
        build_chat_model(),
        instructions=GATE_SYSTEM_PROMPT,
        output_type=RouteDecision,
        model_settings=ModelSettings(temperature=0.0),
        retries=3,
    )


# Passe 2 dédiée : le « relieur ». Décompose l'extraction (entités d'abord, puis
# relations) — un sous-agent à un seul job rate moins ses relations qu'un gros
# tour qui jongle avec tout (cf. sous-extraction mesurée en mono-passe).
RELATION_PERSONA = """\
Tu es le relieur du graphe. Les entités de ce passage existent DÉJÀ dans la base
(consulte-les avec list_entities / describe_schema). Ta SEULE tâche : créer les
relations qui les lient pour ce passage, avec add_relation, avec un type pris
dans le vocabulaire du domaine (CAPITALES anglaises). Si aucun type ne correspond
au lien réel, ce lien ne s'écrit pas — passe au suivant, sans te rabattre sur le
type le plus proche. N'ajoute, ne modifie, ne supprime AUCUNE entité ; si une
entité te semble manquante, ignore-la. Procède relation par relation, puis
confirme en une phrase.
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


def build_master_agent(
    choice: AgentChoice, model: Model | None = None
) -> Agent[GenericDeps, str]:
    """Passe 0 « maître » : MÈNE la conversation (texte streamé), threadée.

    Outils en LECTURE SEULE (find_entity, list_entities) : aucun outil d'écriture
    → il ne PEUT pas inventer d'entité. La décision d'extraire est portée par le
    gate stateless (build_gate_agent), lancé en parallèle par la route — un
    bavardage/une question n'écrit donc RIEN.

    model=None → modèle de chat par défaut. L'override sert l'A/B tiering (#49) :
    le maître est la VOIX du produit (1 appel/tour) et le seul à faire du jugement
    sémantique conversationnel — premier candidat à monter en tier (cf. bug #62)."""
    return create_core_agent(
        profile=choice.profile,
        persona=MASTER_PERSONA,
        system_prompt=MASTER_SYSTEM_PROMPT,
        tools=MASTER_TOOLS,
        model=model,
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
