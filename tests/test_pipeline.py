from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

if TYPE_CHECKING:
    import aiosqlite

import chromadb

from felix.db.queries import get_character_fragments, get_character_profile, list_issues, list_scenes
from felix.db.schema import init_db
from felix.db.seed import seed_db
from felix.ingest.models import (
    CharacterProfile,
    ConsistencyIssue,
    ConsistencyReport,
    ExtractedCharacter,
    ExtractedLocation,
    SceneAnalysis,
)
from felix.ingest.pipeline import ImportProgress, ImportStatus, run_import_pipeline

SCENE_1 = SceneAnalysis(
    title="Arrivee a la planque",
    summary="Marie accueille Sarah a la planque de Lyon.",
    era="1940s",
    approximate_date="1942-03-15",
    characters=[
        ExtractedCharacter(
            name="Marie Dupont", role="participant",
            description="Femme d'une quarantaine d'annees, cheveux bruns",
        ),
        ExtractedCharacter(
            name="Sarah Cohen", role="participant",
            description="Jeune femme apeuree, porte un manteau use",
        ),
    ],
    location=ExtractedLocation(name="Planque de Lyon", description="Rue Merciere"),
    mood="tendu",
)

SCENE_2 = SceneAnalysis(
    title="A la prefecture",
    summary="Benoit copie des documents secrets.",
    era="1940s",
    approximate_date="1942-06-01",
    characters=[
        ExtractedCharacter(
            name="Benoit Laforge", role="participant",
            description="Employe discret, lunettes rondes",
        ),
    ],
    location=ExtractedLocation(name="Prefecture de Lyon", description="Bureau"),
    mood="oppressant",
)

SCENE_3 = SceneAnalysis(
    title="Nouveau personnage",
    summary="Un inconnu arrive en ville.",
    era="1940s",
    approximate_date="1942-07-01",
    characters=[
        ExtractedCharacter(
            name="Jacques Martin", role="participant",
            description="Homme grand, accent du sud",
        ),
    ],
    location=ExtractedLocation(name="Gare de Lyon-Perrache", description="Hall principal"),
    mood="mystere",
)

CONSISTENCY_REPORT = ConsistencyReport(
    issues=[
        ConsistencyIssue(
            type="missing_info",
            severity="warning",
            scene_id="scene-003",
            entity_id="jacques-martin",
            description="Jacques Martin n'a aucun lien avec les autres personnages.",
            suggestion="Ajouter des relations ou du contexte.",
        )
    ]
)


@pytest.fixture
async def db() -> aiosqlite.Connection:
    conn = await init_db(":memory:")
    await seed_db(conn)
    yield conn  # type: ignore[misc]
    await conn.close()


@pytest.fixture
def collection() -> chromadb.Collection:
    client = chromadb.Client()
    return client.get_or_create_collection("test_scenes")


@pytest.fixture
def scenes_dir(tmp_path):
    (tmp_path / "001.txt").write_text("Scene un : Marie accueille Sarah.", encoding="utf-8")
    (tmp_path / "002.txt").write_text("Scene deux : Benoit a la prefecture.", encoding="utf-8")
    (tmp_path / "003.txt").write_text("Scene trois : un inconnu arrive.", encoding="utf-8")
    return str(tmp_path)


def _mock_analyze_scene(analyses: list[SceneAnalysis]):
    call_count = 0

    async def _analyze(_agent, _text):
        nonlocal call_count
        result = analyses[call_count]
        call_count += 1
        return result

    return _analyze


def _mock_check_consistency(report: ConsistencyReport):
    async def _check(_agent, _summary):
        return report

    return _check


MOCK_PROFILE = CharacterProfile(
    age="40 ans",
    physical="Cheveux bruns, taille moyenne",
    background="Resistante lyonnaise",
    arc="De civile a cheffe de reseau",
    traits="Courageuse, determinee",
)


def _mock_profile_character(profile: CharacterProfile):
    async def _profile(_agent, _name, _texts, _fragments):
        return profile

    return _profile


def _pipeline_patches(analyses, report, profile=None):
    """Context manager with all standard pipeline mocks."""
    patches = [
        patch(
            "felix.ingest.pipeline.analyze_scene",
            side_effect=_mock_analyze_scene(analyses),
        ),
        patch(
            "felix.ingest.pipeline.check_consistency",
            side_effect=_mock_check_consistency(report),
        ),
        patch("felix.ingest.pipeline.create_analyzer_agent", return_value=None),
        patch("felix.ingest.pipeline.create_checker_agent", return_value=None),
        patch("felix.ingest.pipeline.create_profiler_agent", return_value=None),
    ]
    if profile is not None:
        patches.append(
            patch(
                "felix.ingest.pipeline.profile_character",
                side_effect=_mock_profile_character(profile),
            )
        )
    else:
        # Default: skip profiling by passing enrich_profiles=False
        pass
    import contextlib
    return contextlib.ExitStack(), patches


async def _run_with_patches(analyses, report, scenes_dir, db, collection, progress, *, enrich_profiles=False, profile=None):
    """Helper to run pipeline with all mocks applied."""
    _, patches = _pipeline_patches(analyses, report, profile)
    if profile is not None:
        # profile mock already in patches
        pass
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        await run_import_pipeline(
            scenes_dir, db, collection, None, None, progress,
            enrich_profiles=enrich_profiles,
        )


import contextlib


async def test_pipeline_full(
    db: aiosqlite.Connection, collection: chromadb.Collection, scenes_dir: str
) -> None:
    progress = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, db, collection, progress,
    )

    assert progress.status == ImportStatus.DONE
    assert progress.processed_scenes == 3
    assert progress.total_scenes == 3

    # Scenes in DB
    scenes = await list_scenes(db)
    assert len(scenes) == 3
    ids = {s["id"] for s in scenes}
    assert "scene-001" in ids
    assert "scene-002" in ids
    assert "scene-003" in ids

    # Issues in DB (1 from consistency check + possible resolver issues)
    issues = await list_issues(db)
    assert any(i["type"] == "missing_info" for i in issues)

    # New entities tracked
    assert "Jacques Martin" in progress.new_characters
    assert "Gare de Lyon-Perrache" in progress.new_locations

    # ChromaDB
    results = collection.get(ids=["scene-001"])
    assert len(results["ids"]) == 1


async def test_pipeline_empty_dir(
    db: aiosqlite.Connection, collection: chromadb.Collection, tmp_path
) -> None:
    progress = ImportProgress()
    await run_import_pipeline(str(tmp_path), db, collection, None, None, progress)
    assert progress.status == ImportStatus.ERROR
    assert "Aucun fichier" in progress.error


async def test_pipeline_idempotent(
    db: aiosqlite.Connection, collection: chromadb.Collection, scenes_dir: str
) -> None:
    progress = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, db, collection, progress,
    )

    # Run again
    progress2 = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, db, collection, progress2,
    )

    assert progress2.status == ImportStatus.DONE
    # Scenes should not duplicate
    scenes = await list_scenes(db)
    assert len(scenes) == 3


async def test_fragments_stored(
    db: aiosqlite.Connection, collection: chromadb.Collection, scenes_dir: str
) -> None:
    """Phase A: character_fragments populated after import."""
    progress = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, db, collection, progress,
    )

    # Marie Dupont should have a fragment for scene-001
    fragments = await get_character_fragments(db, "marie-dupont")
    assert len(fragments) >= 1
    frag = fragments[0]
    assert frag["role"] == "participant"
    assert "quarantaine" in (frag["description"] or "")

    # Jacques Martin (new character) should also have fragments
    fragments_jm = await get_character_fragments(db, "jacques-martin")
    assert len(fragments_jm) == 1
    assert "accent du sud" in (fragments_jm[0]["description"] or "")


async def test_format_profile_includes_fragments(
    db: aiosqlite.Connection, collection: chromadb.Collection, scenes_dir: str
) -> None:
    """Phase A: _format_character_profile includes fragments section."""
    from felix.db.queries import _format_character_profile

    progress = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, db, collection, progress,
    )

    row = await get_character_profile(db, "marie-dupont")
    assert row is not None
    profile_text = await _format_character_profile(db, row)
    assert "Observations par scene" in profile_text
    assert "quarantaine" in profile_text


async def test_profiling_enriches_characters(
    db: aiosqlite.Connection, collection: chromadb.Collection, scenes_dir: str
) -> None:
    """Phase B: profiling fills character profile fields on new characters."""
    progress = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, db, collection, progress,
        enrich_profiles=True, profile=MOCK_PROFILE,
    )

    # Jacques Martin is a new character (not in seed) — all fields should be filled
    row = await get_character_profile(db, "jacques-martin")
    assert row is not None
    assert row["age"] == "40 ans"
    assert row["physical"] == "Cheveux bruns, taille moyenne"
    assert row["background"] == "Resistante lyonnaise"
    assert row["arc"] == "De civile a cheffe de reseau"
    assert row["traits"] == "Courageuse, determinee"


async def test_no_profiling_when_disabled(
    db: aiosqlite.Connection, collection: chromadb.Collection, scenes_dir: str
) -> None:
    """Phase B: enrich_profiles=False keeps profile fields NULL."""
    progress = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, db, collection, progress,
        enrich_profiles=False,
    )

    row = await get_character_profile(db, "jacques-martin")
    assert row is not None
    assert row["age"] is None
    assert row["physical"] is None
    assert row["background"] is None


async def test_coalesce_preserves_existing_data(
    db: aiosqlite.Connection, collection: chromadb.Collection, scenes_dir: str
) -> None:
    """Phase B: COALESCE doesn't overwrite non-null fields."""
    # First run without profiling to create Jacques Martin with NULL fields
    progress = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, db, collection, progress,
    )

    # Manually set age on Jacques Martin
    await db.execute(
        "UPDATE characters SET age = '35 ans' WHERE id = 'jacques-martin'"
    )
    await db.commit()

    # Now run again with profiling
    progress2 = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, db, collection, progress2,
        enrich_profiles=True, profile=MOCK_PROFILE,
    )

    row = await get_character_profile(db, "jacques-martin")
    assert row is not None
    # age should keep the manually set value, not be overwritten by profiler
    assert row["age"] == "35 ans"
    # background was NULL, so profiler fills it
    assert row["background"] == "Resistante lyonnaise"
