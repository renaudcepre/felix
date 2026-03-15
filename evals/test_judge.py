"""LLM judge — tests de qualite semantique avec le vrai modele.

Marques @pytest.mark.eval : ne tournent pas avec pytest seul,
lancer avec : uv run pytest evals/test_judge.py -v
"""
from __future__ import annotations

import pytest

from evals.expected import FIXTURES_DIR, IRINA_ID
from evals.judge import judge_character_profiling, judge_scene_extraction
from felix.config import settings

pytestmark = pytest.mark.eval


async def test_judge_scene_01_extraction(pipeline_export: dict) -> None:
    """Scene 01 : extraction correcte du signal/Irina/Kofi/Helios."""
    scene = next(
        (s for s in pipeline_export["scenes"] if "01" in s["filename"]),
        None,
    )
    assert scene, "scene 01 non trouvee dans l'export"

    scene_text = (FIXTURES_DIR / "01_signal.txt").read_text(encoding="utf-8")
    score = await judge_scene_extraction(
        scene_text,
        {k: scene[k] for k in ("title", "summary", "era", "date")},
        settings.llm_model,
        settings.llm_base_url,
    )
    print(f"\n[judge scene 01] {score.model_dump()}")
    assert score.summary_faithfulness >= 3, (
        f"Resume infidele (note {score.summary_faithfulness}/5) : {score.justification}"
    )
    assert score.characters_completeness >= 3, (
        f"Personnages incomplets (note {score.characters_completeness}/5) : {score.justification}"
    )


async def test_judge_scene_02_extraction(pipeline_export: dict) -> None:
    """Scene 02 : extraction correcte du rapport Chen Wei."""
    scene = next(
        (s for s in pipeline_export["scenes"] if "02" in s["filename"]),
        None,
    )
    assert scene, "scene 02 non trouvee dans l'export"

    scene_text = (FIXTURES_DIR / "02_rapport.txt").read_text(encoding="utf-8")
    score = await judge_scene_extraction(
        scene_text,
        {k: scene[k] for k in ("title", "summary", "era", "date")},
        settings.llm_model,
        settings.llm_base_url,
    )
    print(f"\n[judge scene 02] {score.model_dump()}")
    assert score.summary_faithfulness >= 3, (
        f"Resume infidele (note {score.summary_faithfulness}/5) : {score.justification}"
    )


async def test_judge_irina_profiling(pipeline_export: dict) -> None:
    """Profil d'Irina Voss : ancre dans les textes, pas d'hallucination."""
    irina = next(
        (c for c in pipeline_export["characters"] if c["id"] == IRINA_ID),
        None,
    )
    assert irina, f"{IRINA_ID} non trouve dans l'export"

    # Recupere les textes des scenes ou Irina apparait
    irina_scene_ids = {
        f["scene_id"]
        for f in pipeline_export["character_fragments"]
        if f["character_id"] == IRINA_ID
    }
    scene_texts = [
        s["raw_text"]
        for s in pipeline_export["scenes"]
        if s["id"] in irina_scene_ids and s.get("raw_text")
    ]
    assert scene_texts, "aucun texte de scene pour Irina"

    profile = {
        k: irina.get(k)
        for k in ("background", "arc", "traits")
    }
    score = await judge_character_profiling(
        "Irina Voss",
        scene_texts,
        profile,
        settings.llm_model,
        settings.llm_base_url,
    )
    print(f"\n[judge irina] {score.model_dump()}")
    assert score.no_hallucination, (
        f"Hallucination detectee dans le profil d'Irina : {score.justification}"
    )
    assert score.groundedness >= 3, (
        f"Profil mal ancre (note {score.groundedness}/5) : {score.justification}"
    )
