from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.agent.chat_agent import _build_model
from felix.ingest.models import CharacterProfile

if TYPE_CHECKING:
    from pydantic_ai.models import Model

logger = logging.getLogger("felix.ingest.profiler")

PROFILER_PROMPT = """\
Tu es un assistant specialise dans la synthese de profils de personnages de scenario.

On te donne le nom d'un personnage et les extraits de scenes ou il apparait.
Synthetise un profil structure a partir UNIQUEMENT de ce qui est EXPLICITEMENT \
ecrit dans les textes fournis.

REGLE ABSOLUE : chaque information que tu ecris DOIT pouvoir etre pointee dans \
une phrase precise des textes. Si tu ne peux pas citer la phrase source, \
mets le champ a null. Un champ null est TOUJOURS preferable a une invention.

Ne deduis PAS, n'extrapole PAS, n'embellis PAS. Pas de "probablement", \
pas de "semble", pas de supposition sur l'apparence, les vetements, l'age \
ou le caractere si le texte n'en parle pas.

Champs a remplir :
- age : age ou tranche d'age UNIQUEMENT si le texte le mentionne explicitement
- physical : description physique UNIQUEMENT si le texte decrit l'apparence \
(vetements, traits, corpulence...). "fixait l'ecran" n'est PAS une description physique.
- background : historique et origines UNIQUEMENT ce que le texte dit du passe du personnage
- arc : evolution narrative du personnage a travers les scenes, basee sur ses actions concretes
- traits : traits de caractere UNIQUEMENT ceux demontres par les actions et dialogues du texte
- relations : liste des relations avec d'autres personnages observees dans les textes.
  Pour chaque relation, indique :
  - other_name : le nom exact du personnage tel qu'il apparait dans les textes
  - relation : description libre de la relation (ex: "collegue au relais Helios-3", \
"mentor", "rival", "pere", "IA compagnon"). Sois precis et contextuel.
  Ne liste que les relations clairement presentes dans les textes.

Reponds en francais. Sois concis et factuel.
"""


def create_profiler_agent(
    model_name: str | None = None, base_url: str | None = None
) -> Agent[None, CharacterProfile]:
    model: Model = _build_model(model_name, base_url)
    return Agent(
        model,
        instructions=PROFILER_PROMPT,
        output_type=CharacterProfile,
        model_settings=ModelSettings(temperature=0.1),
        retries=2,
    )


async def profile_character(
    agent: Agent[None, CharacterProfile],
    name: str,
    scene_texts: list[str],
    fragments: list[dict],
    known_characters: list[str] | None = None,
) -> CharacterProfile:
    parts = [f"Personnage : {name}\n"]
    for frag in fragments:
        title = frag.get("scene_title") or frag.get("scene_id", "?")
        role = frag.get("role", "")
        desc = frag.get("description", "")
        parts.append(f"- Scene '{title}' (role: {role}) : {desc}")

    if known_characters:
        parts.append(f"\nPersonnages connus du scenario : {', '.join(known_characters)}")
        parts.append(
            "Pour les relations, utilise les noms exacts de cette liste quand possible."
        )

    parts.append("\nTextes des scenes :")
    for i, text in enumerate(scene_texts, 1):
        parts.append(f"\n--- Scene {i} ---\n{text}")

    input_text = "\n".join(parts)
    result = await agent.run(input_text)
    return result.output
