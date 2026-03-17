from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

if TYPE_CHECKING:
    from neo4j import AsyncDriver

import chromadb

from felix.graph.repository import (
    get_character_fragments,
    get_character_profile,
    get_character_relations,
    list_issues,
    list_scenes,
)
from felix.ingest.models import (
    CharacterProfile,
    ConsistencyIssue,
    ConsistencyReport,
    ExtractedCharacter,
    ExtractedLocation,
    ExtractedRelation,
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


def _mock_check_scene_consistency(report: ConsistencyReport):
    async def _check(_driver, _collection, _scene_summary, _timeline_agent, _narrative_agent):
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
    async def _profile(_agent, _name, _texts, _fragments, _known=None):
        return profile

    return _profile


def _mock_patch_character_profile(profile: CharacterProfile):
    async def _patch(_agent, _name, _existing, _text, _fragment):
        return profile

    return _patch


def _pipeline_patches(analyses, report, profile=None):
    patches = [
        patch(
            "felix.ingest.pipeline.analyze_scene",
            side_effect=_mock_analyze_scene(analyses),
        ),
        patch(
            "felix.ingest.pipeline.check_scene_consistency",
            side_effect=_mock_check_scene_consistency(report),
        ),
        patch("felix.ingest.pipeline.create_analyzer_agent", return_value=None),
        patch("felix.ingest.pipeline.create_checker_agents", return_value=(None, None)),
        patch("felix.ingest.pipeline.create_profiler_agent", return_value=None),
    ]
    if profile is not None:
        patches.append(
            patch(
                "felix.ingest.pipeline.profile_character",
                side_effect=_mock_profile_character(profile),
            )
        )
        patches.append(
            patch(
                "felix.ingest.pipeline.patch_character_profile",
                side_effect=_mock_patch_character_profile(profile),
            )
        )
    return patches


async def _run_with_patches(analyses, report, scenes_dir, driver, collection, progress, *, enrich_profiles=False, profile=None):
    patches = _pipeline_patches(analyses, report, profile)
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        await run_import_pipeline(
            scenes_dir, driver, collection, None, None, progress,
            enrich_profiles=enrich_profiles,
        )


async def test_pipeline_full(
    seeded_driver: AsyncDriver, collection: chromadb.Collection, scenes_dir: str
) -> None:
    progress = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, seeded_driver, collection, progress,
    )

    assert progress.status == ImportStatus.DONE
    assert progress.processed_scenes == 3
    assert progress.total_scenes == 3

    scenes = await list_scenes(seeded_driver)
    assert len(scenes) == 3
    ids = {s["id"] for s in scenes}
    assert "scene-001" in ids
    assert "scene-002" in ids
    assert "scene-003" in ids

    issues = await list_issues(seeded_driver)
    assert any(i["type"] == "missing_info" for i in issues)

    assert "Jacques Martin" in progress.new_characters
    assert "Gare de Lyon-Perrache" in progress.new_locations

    results = collection.get(ids=["scene-001"])
    assert len(results["ids"]) == 1


async def test_pipeline_empty_dir(
    seeded_driver: AsyncDriver, collection: chromadb.Collection, tmp_path
) -> None:
    progress = ImportProgress()
    await run_import_pipeline(str(tmp_path), seeded_driver, collection, None, None, progress)
    assert progress.status == ImportStatus.ERROR
    assert "Aucun fichier" in progress.error


async def test_pipeline_idempotent(
    seeded_driver: AsyncDriver, collection: chromadb.Collection, scenes_dir: str
) -> None:
    progress = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, seeded_driver, collection, progress,
    )

    progress2 = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, seeded_driver, collection, progress2,
    )

    assert progress2.status == ImportStatus.DONE
    scenes = await list_scenes(seeded_driver)
    assert len(scenes) == 3


async def test_fragments_stored(
    seeded_driver: AsyncDriver, collection: chromadb.Collection, scenes_dir: str
) -> None:
    progress = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, seeded_driver, collection, progress,
    )

    fragments = await get_character_fragments(seeded_driver, "marie-dupont")
    assert len(fragments) >= 1
    frag = fragments[0]
    assert frag["role"] == "participant"
    assert "quarantaine" in (frag["description"] or "")

    fragments_jm = await get_character_fragments(seeded_driver, "jacques-martin")
    assert len(fragments_jm) == 1
    assert "accent du sud" in (fragments_jm[0]["description"] or "")


async def test_format_profile_includes_fragments(
    seeded_driver: AsyncDriver, collection: chromadb.Collection, scenes_dir: str
) -> None:
    from felix.graph.formatters import find_character

    progress = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, seeded_driver, collection, progress,
    )

    profile_text = await find_character(seeded_driver, "marie")
    assert "Observations par scene" in profile_text
    assert "quarantaine" in profile_text


async def test_profiling_enriches_characters(
    seeded_driver: AsyncDriver, collection: chromadb.Collection, scenes_dir: str
) -> None:
    progress = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, seeded_driver, collection, progress,
        enrich_profiles=True, profile=MOCK_PROFILE,
    )

    row = await get_character_profile(seeded_driver, "jacques-martin")
    assert row is not None
    assert row["age"] == "40 ans"
    assert row["physical"] == "Cheveux bruns, taille moyenne"
    assert row["background"] == "Resistante lyonnaise"
    assert row["arc"] == "De civile a cheffe de reseau"
    assert row["traits"] == "Courageuse, determinee"


async def test_no_profiling_when_disabled(
    seeded_driver: AsyncDriver, collection: chromadb.Collection, scenes_dir: str
) -> None:
    progress = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, seeded_driver, collection, progress,
        enrich_profiles=False,
    )

    row = await get_character_profile(seeded_driver, "jacques-martin")
    assert row is not None
    assert row.get("age") is None
    assert row.get("physical") is None
    assert row.get("background") is None


async def test_coalesce_preserves_existing_data(
    seeded_driver: AsyncDriver, collection: chromadb.Collection, scenes_dir: str
) -> None:
    progress = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, seeded_driver, collection, progress,
    )

    # Manually set age on Jacques Martin
    async with seeded_driver.session() as session:
        await session.run(
            "MATCH (c:Character {id: 'jacques-martin'}) SET c.age = '35 ans'"
        )

    progress2 = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, seeded_driver, collection, progress2,
        enrich_profiles=True, profile=MOCK_PROFILE,
    )

    row = await get_character_profile(seeded_driver, "jacques-martin")
    assert row is not None
    assert row["age"] == "35 ans"
    assert row["background"] == "Resistante lyonnaise"


MOCK_PROFILE_WITH_RELATIONS = CharacterProfile(
    age="30 ans",
    physical="Grande, cheveux noirs",
    background="Ingenieure",
    arc="Decouvre un signal inconnu",
    traits="Determinee, curieuse",
    relations=[
        ExtractedRelation(other_name="Marie Dupont", relation="collegue de resistance"),
    ],
)


async def test_profiling_stores_relations(
    seeded_driver: AsyncDriver, collection: chromadb.Collection, scenes_dir: str
) -> None:
    progress = ImportProgress()
    await _run_with_patches(
        [SCENE_1, SCENE_2, SCENE_3], CONSISTENCY_REPORT,
        scenes_dir, seeded_driver, collection, progress,
        enrich_profiles=True, profile=MOCK_PROFILE_WITH_RELATIONS,
    )

    rels = await get_character_relations(seeded_driver, "jacques-martin")
    assert len(rels) >= 1
    rel_names = [r["other_name"] for r in rels]
    assert "Marie Dupont" in rel_names
