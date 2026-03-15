from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic_ai import Agent, ModelRetry
from pydantic_ai.settings import ModelSettings

from felix.agent.chat_agent import _build_model
from felix.ingest.models import SceneAnalysis

if TYPE_CHECKING:
    from pydantic_ai.models import Model

logger = logging.getLogger("felix.ingest.analyzer")

ANALYZER_PROMPT = """\
Tu es un assistant specialise dans l'analyse de scenes de scenario.

A partir du texte d'une scene, extrais les informations suivantes :
- title : titre court en francais (max 10 mots)
- summary : resume en 2-3 phrases en francais
- era : epoque par decennie ("2050s", "2140s", "1940s", etc.)
- approximate_date : date au format YYYY-MM-DD si deductible du texte. \
Si seule l'annee est connue, utilise YYYY-01-01. \
Si l'annee et le mois sont connus, utilise YYYY-MM-01. Ne retourne null que si AUCUNE indication temporelle
- characters : liste des personnages avec leur role et description si presente
- location : lieu principal de la scene avec description si presente
- mood : ambiance generale en un mot ou une courte expression

PERSONNAGES — EXTRAIS TOUS LES PERSONNAGES, y compris ceux simplement evoques ou mentionnes en passant :
- "participant" : le personnage AGIT physiquement dans la scene (parle, bouge, fait quelque chose)
- "witness" : le personnage est PRESENT dans la scene mais n'agit pas directement
- "mentioned" : le personnage est EVOQUE par un autre, dans un dialogue, dans la narration, ou dans un souvenir — meme brievement. Inclut les ancetres, parents, personnes referees par nom.

IMPORTANT : si un personnage est nomme ne serait-ce qu'UNE SEULE FOIS dans le texte (ex: "le fils d'Elias", "comme disait Jakes"), il DOIT apparaitre dans la liste avec le role "mentioned".

Un personnage qui est un ancetre, un parent, un souvenir, ou dont on parle au passe est "mentioned", PAS "participant".

NOMS DE PERSONNAGES :
- Utilise UNIQUEMENT le nom propre du personnage (prenom + nom de famille).
- Ne mets PAS le titre, le metier ou le rang dans le champ "name" \
(pas "Docteur Jean Martin" mais "Jean Martin", pas "Capitaine Korvin" mais "Lara Korvin").
- Le metier ou le rang doit aller dans le champ "description", pas dans "name".

REGLES :
- N'invente RIEN. Extrais uniquement ce qui est dans le texte.
- Reponds en francais.
- Si une information n'est pas dans le texte, utilise null.
- Chaque personnage ne doit apparaitre QU'UNE SEULE FOIS dans la liste.
"""


def create_analyzer_agent(
    model_name: str | None = None, base_url: str | None = None
) -> Agent[None, SceneAnalysis]:
    model: Model = _build_model(model_name, base_url)
    agent: Agent[None, SceneAnalysis] = Agent(
        model,
        instructions=ANALYZER_PROMPT,
        output_type=SceneAnalysis,
        model_settings=ModelSettings(temperature=0.1),
        retries=2,
    )

    @agent.output_validator
    def validate_output(output: SceneAnalysis) -> SceneAnalysis:
        if len(output.characters) < 1:
            raise ModelRetry("La scene doit contenir au moins un personnage")
        return output

    return agent


async def analyze_scene(
    agent: Agent[None, SceneAnalysis], scene_text: str
) -> SceneAnalysis:
    result = await agent.run(scene_text)
    return result.output
