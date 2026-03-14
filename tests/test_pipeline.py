from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

if TYPE_CHECKING:
    import aiosqlite

import chromadb

from felix.db.queries import list_issues, list_scenes
from felix.db.schema import init_db
from felix.db.seed import seed_db
from felix.ingest.models import (
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
        ExtractedCharacter(name="Marie Dupont", role="participant"),
        ExtractedCharacter(name="Sarah Cohen", role="participant"),
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
        ExtractedCharacter(name="Benoit Laforge", role="participant"),
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
        ExtractedCharacter(name="Jacques Martin", role="participant"),
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


async def test_pipeline_full(
    db: aiosqlite.Connection, collection: chromadb.Collection, scenes_dir: str
) -> None:
    progress = ImportProgress()

    with (
        patch(
            "felix.ingest.pipeline.analyze_scene",
            side_effect=_mock_analyze_scene([SCENE_1, SCENE_2, SCENE_3]),
        ),
        patch(
            "felix.ingest.pipeline.check_consistency",
            side_effect=_mock_check_consistency(CONSISTENCY_REPORT),
        ),
        patch("felix.ingest.pipeline.create_analyzer_agent", return_value=None),
        patch("felix.ingest.pipeline.create_checker_agent", return_value=None),
    ):
        await run_import_pipeline(scenes_dir, db, collection, None, None, progress)

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

    with (
        patch(
            "felix.ingest.pipeline.analyze_scene",
            side_effect=_mock_analyze_scene([SCENE_1, SCENE_2, SCENE_3]),
        ),
        patch(
            "felix.ingest.pipeline.check_consistency",
            side_effect=_mock_check_consistency(CONSISTENCY_REPORT),
        ),
        patch("felix.ingest.pipeline.create_analyzer_agent", return_value=None),
        patch("felix.ingest.pipeline.create_checker_agent", return_value=None),
    ):
        await run_import_pipeline(scenes_dir, db, collection, None, None, progress)

    # Run again
    progress2 = ImportProgress()
    with (
        patch(
            "felix.ingest.pipeline.analyze_scene",
            side_effect=_mock_analyze_scene([SCENE_1, SCENE_2, SCENE_3]),
        ),
        patch(
            "felix.ingest.pipeline.check_consistency",
            side_effect=_mock_check_consistency(CONSISTENCY_REPORT),
        ),
        patch("felix.ingest.pipeline.create_analyzer_agent", return_value=None),
        patch("felix.ingest.pipeline.create_checker_agent", return_value=None),
    ):
        await run_import_pipeline(scenes_dir, db, collection, None, None, progress2)

    assert progress2.status == ImportStatus.DONE
    # Scenes should not duplicate
    scenes = await list_scenes(db)
    assert len(scenes) == 3
