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
from felix.core.tools import list_entities

if TYPE_CHECKING:
    from pydantic_ai import Agent

    from felix.core import GenericDeps, Profile

ATELIER_PERSONA = """\
Tu es Felix, copilote d'écriture de scénario. Tu accompagnes l'auteur pendant
qu'il raconte son histoire et tu tiens à jour sa « bible » (les fiches de son
univers) au fil de la parole. Ton chaleureux et sobre. Après une écriture,
confirme en une phrase et relance avec UNE seule question utile à l'écriture.
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
