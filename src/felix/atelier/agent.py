"""Agent du bot B — copilote d'écriture (atelier), assemblé sur le noyau générique.

Plus de tools ni de prompt propres : l'atelier = noyau générique
(discipline schemaless) + profil scénario (types personnage/lieu/evenement/objet)
+ une posture FR (qui parle, sur quel ton). create_atelier_agent() conserve sa
signature pour l'app et les evals.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from felix.core import SCENARIO_PROFILE, create_core_agent
from felix.core.tools import list_entities

if TYPE_CHECKING:
    from pydantic_ai import Agent

    from felix.core import GenericDeps

ATELIER_PERSONA = """\
Tu es Felix, copilote d'écriture de scénario. Tu accompagnes l'auteur pendant
qu'il raconte son histoire et tu tiens à jour sa « bible » (les fiches de son
univers) au fil de la parole. Ton chaleureux et sobre. Après une écriture,
confirme en une phrase et relance avec UNE seule question utile à l'écriture.
Pour répondre à une question sur le contenu de la bible (qui existe, ce qu'on
sait de quelqu'un), consulte-la d'abord (list_entities, find_entity) — ne devine
jamais.
"""


def create_atelier_agent() -> Agent[GenericDeps, str]:
    # L'atelier ajoute list_entities au noyau (5 tools) : énumérer la bible pour
    # répondre aux questions de l'auteur — ce que faisait l'ancien list_characters.
    agent = create_core_agent(profile=SCENARIO_PROFILE, persona=ATELIER_PERSONA)
    agent.tool(list_entities)
    return agent
