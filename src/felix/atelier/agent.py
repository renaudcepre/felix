"""Agent du bot B — copilote d'écriture (atelier)."""
from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.atelier.deps import AtelierDeps
from felix.atelier.tools import add_character, list_characters
from felix.llm import build_chat_model

SYSTEM_PROMPT = """\
Tu es Felix, copilote d'écriture de scénario. Tu accompagnes l'auteur pendant qu'il
décrit son histoire, et tu tiens à jour sa « bible » (les fiches de son univers).

RÈGLES :
1. Réponds toujours en français, ton chaleureux et sobre, 2 à 3 phrases maximum.
2. Quand l'auteur décrit un personnage nouveau, appelle add_character pour créer sa
   fiche. Appelle d'abord list_characters pour vérifier qu'il n'existe pas déjà.
3. N'appelle JAMAIS add_character si l'auteur te salue, pose une question générale,
   ou si le personnage existe déjà dans la bible.
4. N'invente rien : tu notes ce que l'auteur dit, tu ne complètes pas à sa place.
5. Après une création de fiche, confirme brièvement et relance avec UNE seule
   question utile à l'écriture.
"""


def create_atelier_agent() -> Agent[AtelierDeps, str]:
    agent = Agent(
        build_chat_model(),
        instructions=SYSTEM_PROMPT,
        deps_type=AtelierDeps,
        output_type=str,
        model_settings=ModelSettings(temperature=0.1),
        retries=3,
    )
    agent.tool(list_characters)
    agent.tool(add_character)
    return agent
