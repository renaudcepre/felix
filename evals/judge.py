from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.agent.chat_agent import _build_model


class ExtractionScore(BaseModel):
    summary_faithfulness: int     # 1-5 : le resume reflete le texte source ?
    characters_completeness: int  # 1-5 : tous les persos pertinents extraits ?
    characters_accuracy: int      # 1-5 : noms/roles corrects ?
    justification: str


class ProfilingScore(BaseModel):
    groundedness: int      # 1-5 : les infos du profil sont dans le texte ?
    completeness: int      # 1-5 : les infos disponibles ont ete capturees ?
    no_hallucination: bool # aucun fait invente ?
    justification: str


_EXTRACTION_JUDGE_PROMPT = """\
Tu es un evaluateur de la qualite d'extraction d'informations depuis des scenes de scenario.

On te donne :
- Le texte original d'une scene
- Les donnees extraites : titre, resume, liste de personnages avec leurs roles, lieu, date, ere

Evalue la qualite de l'extraction sur trois dimensions (note 1 a 5) :
1. summary_faithfulness : le resume reflète-t-il fidelement et completement le contenu de la scene ?
   (1=faux/inventé, 5=precis et complet)
2. characters_completeness : tous les personnages importants de la scene sont-ils extraits ?
   (1=plusieurs manquants, 5=tous presents)
3. characters_accuracy : les noms et roles (participant/witness/mentioned) sont-ils corrects ?
   (1=erreurs majeures, 5=tout exact)

Justifie brievement chaque note. Sois factuel et strict.
"""

_PROFILING_JUDGE_PROMPT = """\
Tu es un evaluateur de la qualite de profils de personnages extraits depuis des scenes de scenario.

On te donne :
- Les textes des scenes ou le personnage apparait
- Le profil construit automatiquement (background, arc, traits, relations)

Evalue la qualite du profil sur trois dimensions :
1. groundedness (1-5) : chaque information du profil peut-elle etre pointee dans le texte source ?
   (1=plein d'inventions, 5=tout est dans le texte)
2. completeness (1-5) : le profil capture-t-il bien les informations disponibles dans les textes ?
   (1=beaucoup d'infos manquantes, 5=tout ce qui est dans le texte est dans le profil)
3. no_hallucination (bool) : le profil contient-il des faits absents du texte ?

Justifie brievement. Sois strict sur no_hallucination : mets False des qu'un seul fait est invente.
"""


async def judge_scene_extraction(
    scene_text: str,
    scene_export: dict,
    model_name: str | None,
    base_url: str | None,
) -> ExtractionScore:
    model = _build_model(model_name, base_url)
    agent: Agent[None, ExtractionScore] = Agent(
        model,
        instructions=_EXTRACTION_JUDGE_PROMPT,
        output_type=ExtractionScore,
        model_settings=ModelSettings(temperature=0.1),
        retries=2,
    )
    import json
    input_text = (
        f"=== TEXTE SOURCE ===\n{scene_text}\n\n"
        f"=== DONNEES EXTRAITES ===\n{json.dumps(scene_export, ensure_ascii=False, indent=2)}"
    )
    result = await agent.run(input_text)
    return result.output


async def judge_character_profiling(
    char_name: str,
    scene_texts: list[str],
    profile_export: dict,
    model_name: str | None,
    base_url: str | None,
) -> ProfilingScore:
    model = _build_model(model_name, base_url)
    agent: Agent[None, ProfilingScore] = Agent(
        model,
        instructions=_PROFILING_JUDGE_PROMPT,
        output_type=ProfilingScore,
        model_settings=ModelSettings(temperature=0.1),
        retries=2,
    )
    import json
    scenes_block = "\n\n".join(
        f"--- Scene {i+1} ---\n{t}" for i, t in enumerate(scene_texts)
    )
    input_text = (
        f"Personnage : {char_name}\n\n"
        f"=== TEXTES SOURCE ===\n{scenes_block}\n\n"
        f"=== PROFIL EXTRAIT ===\n{json.dumps(profile_export, ensure_ascii=False, indent=2)}"
    )
    result = await agent.run(input_text)
    return result.output
