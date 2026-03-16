from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from felix.agent.chat_agent import _build_model
from felix.db.repository import get_scene_summaries_by_ids
from felix.ingest.models import ConsistencyReport

if TYPE_CHECKING:
    import aiosqlite
    import chromadb
    from pydantic_ai.models import Model

logger = logging.getLogger("felix.ingest.checker")

CHECKER_TIMELINE_PROMPT = """\
Tu es un assistant specialise dans la verification de coherence temporelle de scenarios.

On te donne une liste de scenes triees chronologiquement (scene_id, titre, resume, date, era).

CONTEXTE IMPORTANT :
- Les scenes peuvent couvrir plusieurs epoques (ex: 1940s, 1970s, 2050s, 2140s).
- Des personnages avec le meme nom de famille peuvent etre des personnes DIFFERENTES.
- Une entite (objet, IA, organisation) peut EVOLUER au fil du temps — ce n'est PAS une incoherence.

Detecte UNIQUEMENT les vraies incoherences TEMPORELLES :
- timeline_inconsistency : dates impossibles, anachronismes, evenements dans le mauvais ordre,
  dates contradictoires entre scenes

NE SIGNALE PAS :
- Des personnages de la meme famille avec des noms similaires (ce sont des personnes differentes)
- L'evolution normale d'une entite au fil du temps
- Toute incoherence non temporelle (contradictions de personnages, infos manquantes...)

Pour chaque probleme, fournis :
- type : "timeline_inconsistency"
- severity : "error" (certaine) ou "warning" (suspicion)
- scene_id : l'ID de la scene concernee
- entity_id : l'ID de l'entite concernee si applicable, sinon null
- description : description claire en francais
- suggestion : suggestion de correction en francais

Si tout est coherent, retourne une liste vide d'issues.
"""

CHECKER_NARRATIVE_PROMPT = """\
Tu es un assistant specialise dans la verification de coherence narrative de scenarios.

On te donne :
- "current_scene" : la scene a verifier (scene_id, titre, resume, personnages, lieu)
- "related_scenes" : les scenes semantiquement proches (scene_id, titre, resume)

CONTEXTE IMPORTANT :
- Des personnages avec le meme nom de famille peuvent etre des personnes DIFFERENTES.
- Un personnage avec le role "mentioned" n'est PAS physiquement present — il est juste evoque.
- Un personnage mort peut etre mentionne dans des scenes posterieures — ce n'est PAS une incoherence.

Detecte UNIQUEMENT les vraies incoherences NARRATIVES dans la scene courante :
- character_contradiction : un personnage fait quelque chose d'incompatible avec ce qu'on
  sait de lui dans les scenes precedentes (meme personnage, pas un homonyme ou descendant)
- missing_info : un personnage reagit a une information qu'il ne peut pas encore connaitre
  d'apres les scenes precedentes

NE SIGNALE PAS :
- Les incoherences temporelles (dates, anachronismes) — ce n'est pas votre domaine
- Des personnages de la meme famille avec des noms similaires
- L'evolution normale d'entites au fil du temps

Pour chaque probleme, fournis :
- type : "character_contradiction" ou "missing_info"
- severity : "error" (certaine) ou "warning" (suspicion)
- scene_id : l'ID de la scene concernee (le scene_id de la current_scene)
- entity_id : l'ID de l'entite concernee si applicable, sinon null
- description : description claire en francais
- suggestion : suggestion de correction en francais

Si tout est coherent, retourne une liste vide d'issues.
"""


def _create_checker_agent(
    prompt: str,
    model_name: str | None = None,
    base_url: str | None = None,
) -> Agent[None, ConsistencyReport]:
    model: Model = _build_model(model_name, base_url)
    return Agent(
        model,
        instructions=prompt,
        output_type=ConsistencyReport,
        model_settings=ModelSettings(temperature=0.1),
        retries=2,
    )


def create_checker_agents(
    model_name: str | None = None,
    base_url: str | None = None,
) -> tuple[Agent[None, ConsistencyReport], Agent[None, ConsistencyReport]]:
    """Create timeline and narrative checker agents (one-time, reusable)."""
    return (
        _create_checker_agent(CHECKER_TIMELINE_PROMPT, model_name, base_url),
        _create_checker_agent(CHECKER_NARRATIVE_PROMPT, model_name, base_url),
    )


async def check_scene_consistency(
    db: aiosqlite.Connection,
    collection: chromadb.Collection,
    scene_summary: dict[str, Any],
    timeline_agent: Agent[None, ConsistencyReport],
    narrative_agent: Agent[None, ConsistencyReport],
) -> ConsistencyReport:
    current_scene_id = scene_summary["scene_id"]

    # 1. Retrieval ChromaDB
    char_names = [c["name"] for c in scene_summary.get("characters", [])]
    location_name = scene_summary.get("location", {}).get("name", "")
    query_text = f"{' '.join(char_names)} {location_name}".strip()

    relevant_summaries: list[dict[str, Any]] = []
    if query_text:
        total = collection.count()
        n = min(11, total)
        if n > 0:
            results = collection.query(query_texts=[query_text], n_results=n)
            metadatas = results.get("metadatas") or [[]]
            relevant_ids: list[str] = [
                str(m["scene_id"])
                for m in metadatas[0]
                if m.get("scene_id") and m["scene_id"] != current_scene_id
            ][:10]
            if relevant_ids:
                relevant_summaries = await get_scene_summaries_by_ids(db, relevant_ids)

    # 2. Pass 1 — Timeline
    timeline_scenes = [
        {
            "scene_id": s["id"],
            "era": s["era"],
            "date": s["date"],
            "title": s["title"],
            "summary": s["summary"],
        }
        for s in relevant_summaries
    ] + [
        {
            "scene_id": current_scene_id,
            "era": scene_summary.get("era"),
            "date": scene_summary.get("date"),
            "title": scene_summary.get("title"),
            "summary": scene_summary.get("summary"),
        }
    ]
    timeline_scenes.sort(key=lambda s: (s["date"] is None, s["date"] or ""))

    timeline_result = await timeline_agent.run(
        json.dumps(timeline_scenes, ensure_ascii=False, indent=2)
    )
    timeline_report = timeline_result.output

    # 3. Pass 2 — Narrative
    narrative_input = {
        "current_scene": {
            "scene_id": current_scene_id,
            "title": scene_summary.get("title"),
            "summary": scene_summary.get("summary"),
            "characters": scene_summary.get("characters", []),
            "location": scene_summary.get("location", {}),
        },
        "related_scenes": [
            {
                "scene_id": s["id"],
                "title": s["title"],
                "summary": s["summary"],
            }
            for s in relevant_summaries
        ],
    }

    narrative_result = await narrative_agent.run(
        json.dumps(narrative_input, ensure_ascii=False, indent=2)
    )
    narrative_report = narrative_result.output

    return ConsistencyReport(issues=timeline_report.issues + narrative_report.issues)
