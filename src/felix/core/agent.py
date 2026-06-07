"""Agent du noyau générique — discipline schemaless, domaine et posture injectés.

create_core_agent assemble les instructions en trois couches :
1. ``persona``  — qui parle, sur quel ton (vide pour le noyau nu) ;
2. SYSTEM_PROMPT — la discipline schemaless, commune à tous les domaines ;
3. ``profile``  — le bloc « === DOMAINE === » qui oriente vers un domaine donné.

Sans argument, create_core_agent() reproduit le comportement du prototype
générique (discipline seule, aucun domaine).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.core.deps import GenericDeps
from felix.core.tools import (
    add_entity,
    add_relation,
    describe_schema,
    find_entity,
    update_entity,
)
from felix.llm import build_chat_model

if TYPE_CHECKING:
    from felix.core.profile import Profile

SYSTEM_PROMPT = """\
Tu maintiens une base de connaissances structurée (entités, propriétés,
relations) au fil de la conversation, quel que soit le domaine.

RÈGLES :
1. Avant toute écriture, appelle describe_schema pour connaître les types
   d'entités et les noms de propriétés déjà utilisés dans la base.
2. RÉUTILISE toujours les types et les noms de propriétés existants quand le
   sens correspond. Ne crée JAMAIS deux noms pour le même concept : si
   `date_achat` existe, n'invente pas `achete_en`.
3. Une chose nouvelle → add_entity. Une information sur une chose connue →
   update_entity. Quand deux entités nommées apparaissent dans la même phrase,
   crée chacune ET la relation qui les lie (add_relation).
4. Ne REMPLACE une valeur existante que si l'utilisateur corrige explicitement
   (« correction », « en fait », « plutôt »). Une information qui DIVERGE d'une
   valeur existante (autre source, témoignage…) s'AJOUTE — nouvelle propriété
   ou relation — sans toucher la valeur en place.
5. N'écris RIEN si l'utilisateur te salue, pose une question ou ne donne
   aucun fait nouveau.
6. N'invente aucun fait : tu enregistres ce que l'utilisateur dit, rien de plus.
7. Réponds en français, 2 phrases maximum.
"""


def create_core_agent(
    profile: Profile | None = None, persona: str = ""
) -> Agent[GenericDeps, str]:
    instructions = SYSTEM_PROMPT
    if persona:
        instructions = persona.rstrip() + "\n\n" + instructions
    if profile is not None:
        instructions = instructions.rstrip() + "\n\n" + profile.render_prompt_block()

    agent = Agent(
        build_chat_model(),
        instructions=instructions,
        deps_type=GenericDeps,
        output_type=str,
        model_settings=ModelSettings(temperature=0.1),
        retries=3,
    )
    agent.tool(describe_schema)
    agent.tool(find_entity)
    agent.tool(add_entity)
    agent.tool(update_entity)
    agent.tool(add_relation)
    return agent
