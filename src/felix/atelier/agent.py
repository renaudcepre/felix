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

# Le maître ne décide PLUS de l'extraction (cf. GATE ci-dessous) : il est purement
# conversationnel. L'enregistrement étant géré ailleurs, la seule discipline qui
# reste est de ne jamais l'annoncer (« noté ») et de ne jamais deviner la bible.
MASTER_SYSTEM_PROMPT = """\
Tu mènes une conversation d'écriture. Tu ne touches JAMAIS à la base toi-même :
tu peux seulement la LIRE (find_entity, list_entities). L'enregistrement des
fiches est géré ailleurs, automatiquement : ne dis JAMAIS « noté » / « j'enregistre »
(les fiches s'affichent d'elles-mêmes à côté de la conversation).

Réponds à l'auteur en 1 à 2 phrases : réagis à l'HISTOIRE, puis relance avec UNE
seule question utile à l'écriture. Pour une question sur ce qui existe (« qui est
X ? », « qu'a-t-on sur Y ? »), consulte la bible (find_entity / list_entities) —
ne devine jamais.

Réponds en français, 2 phrases maximum.
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
    """Passe 0 « maître » : MÈNE la conversation (texte streamé), threadée.

    Outils en LECTURE SEULE (find_entity, list_entities) : aucun outil d'écriture
    → il ne PEUT pas inventer d'entité. La décision d'extraire est portée par le
    gate stateless (build_gate_agent), lancé en parallèle par la route — un
    bavardage/une question n'écrit donc RIEN."""
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
