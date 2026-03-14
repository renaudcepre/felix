from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.agent.chat_agent import _build_model
from felix.ingest.models import CharacterProfile

if TYPE_CHECKING:
    from pydantic_ai.models import Model

PROFILER_PROMPT = """\
Tu es un assistant specialise dans la synthese de profils de personnages de scenario.

On te donne le nom d'un personnage et les extraits de scenes ou il apparait.
Synthetise un profil structure a partir UNIQUEMENT de ce qui est dans les textes.

N'INVENTE RIEN. Si une information n'est pas dans les textes, laisse le champ a null.

Champs a remplir :
- age : age approximatif ou tranche d'age deduite du texte
- physical : description physique (apparence, vetements, traits distinctifs)
- background : historique, passe, origines du personnage
- arc : evolution narrative du personnage a travers les scenes
- traits : traits de caractere, personnalite, manieres

Reponds en francais. Sois concis mais precis.
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
    )


async def profile_character(
    agent: Agent[None, CharacterProfile],
    name: str,
    scene_texts: list[str],
    fragments: list[dict],
) -> CharacterProfile:
    parts = [f"Personnage : {name}\n"]
    for frag in fragments:
        title = frag.get("scene_title") or frag.get("scene_id", "?")
        role = frag.get("role", "")
        desc = frag.get("description", "")
        parts.append(f"- Scene '{title}' (role: {role}) : {desc}")

    parts.append("\nTextes des scenes :")
    for i, text in enumerate(scene_texts, 1):
        parts.append(f"\n--- Scene {i} ---\n{text}")

    input_text = "\n".join(parts)
    result = await agent.run(input_text)
    return result.output
