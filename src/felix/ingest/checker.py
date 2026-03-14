from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.agent.chat_agent import _build_model
from felix.ingest.models import ConsistencyReport

if TYPE_CHECKING:
    from pydantic_ai.models import Model

CHECKER_PROMPT = """\
Tu es un assistant specialise dans la verification de coherence de scenarios.

On te donne un resume JSON de toutes les scenes importees (titre, resume, date, era, personnages, lieu).

CONTEXTE IMPORTANT :
- Les scenes peuvent couvrir plusieurs epoques (ex: 1940s, 1970s, 2050s, 2140s).
- Des personnages avec le meme nom de famille peuvent etre des personnes DIFFERENTES (parent, enfant, ancetre, descendant). Ne les confonds pas.
- Une entite (objet, IA, organisation) peut EVOLUER au fil du temps : un drone peut devenir une IA globale, une mine peut devenir un datacenter. Ce n'est PAS une incoherence.
- Un personnage "mentioned" dans une scene n'est PAS physiquement present — il est juste evoque. Ne signale pas d'incoherence pour un personnage mort qui est simplement mentionne plus tard.

Detecte UNIQUEMENT les vraies incoherences :
- timeline_inconsistency : dates impossibles, anachronismes, evenements contradictoires dans le mauvais ordre
- character_contradiction : un personnage fait quelque chose d'incompatible avec ce qu'on sait de lui (meme personnage, pas un homonyme ou descendant)
- missing_info : informations critiques manquantes (date, lieu, personnages non identifies)

NE SIGNALE PAS :
- Des personnages de la meme famille avec des noms similaires (ce sont des personnes differentes)
- L'evolution normale d'une entite au fil du temps
- Un personnage mort qui est mentionne ou evoque dans des scenes posterieures

Pour chaque vrai probleme, fournis :
- type : le type d'incoherence
- severity : "error" (incoherence certaine) ou "warning" (suspicion)
- scene_id : l'ID de la scene concernee
- entity_id : l'ID de l'entite concernee si applicable, sinon null
- description : description claire en francais
- suggestion : suggestion de correction en francais

Si tout est coherent, retourne une liste vide d'issues.
"""


def create_checker_agent(
    model_name: str | None = None, base_url: str | None = None
) -> Agent[None, ConsistencyReport]:
    model: Model = _build_model(model_name, base_url)
    return Agent(
        model,
        instructions=CHECKER_PROMPT,
        output_type=ConsistencyReport,
        model_settings=ModelSettings(temperature=0.1),
    )


async def check_consistency(
    agent: Agent[None, ConsistencyReport],
    scenes_summary: list[dict[str, Any]],
) -> ConsistencyReport:
    input_text = json.dumps(scenes_summary, ensure_ascii=False, indent=2)
    result = await agent.run(input_text)
    return result.output
