from __future__ import annotations

import asyncio
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
from felix.ingest.pipeline import (
    ClarificationSlot,
    ImportProgress,
    ImportStatus,
    _handle_ambiguous_character,
    _resolve_location,
    run_import_pipeline,
)
from felix.ingest.resolver import AmbiguousMatch

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
    async def _profile(_agent, _name, _texts, _fragments, _known=None, **kwargs):
        return profile

    return _profile


def _mock_patch_character_profile(profile: CharacterProfile):
    async def _patch(_agent, _name, _existing, _text, _fragment, **kwargs):
        return profile

    return _patch


def _pipeline_patches(analyses, report, profile=None):
    patches = [
        patch(
            "felix.ingest.orchestrator.analyze_scene",
            side_effect=_mock_analyze_scene(analyses),
        ),
        patch(
            "felix.ingest.orchestrator.check_scene_consistency",
            side_effect=_mock_check_scene_consistency(report),
        ),
        patch("felix.ingest.pipeline.create_analyzer_agent", return_value=None),
        patch("felix.ingest.pipeline.create_checker_agents", return_value=(None, None)),
        patch("felix.ingest.pipeline.create_profiler_agent", return_value=None),
        patch("felix.ingest.pipeline.create_profiler_patch_agent", return_value=None),
        patch("felix.ingest.pipeline.create_beat_extractor_agent", return_value=None),
        patch("felix.ingest.pipeline.shutil.rmtree"),
    ]
    if profile is not None:
        patches.append(
            patch(
                "felix.ingest.orchestrator.profile_character",
                side_effect=_mock_profile_character(profile),
            )
        )
        patches.append(
            patch(
                "felix.ingest.orchestrator.patch_character_profile",
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


# --- Tests issue #18 : duplicate_suspect resolved selon confirmation ou timeout ---

def _make_ambiguous_match() -> AmbiguousMatch:
    return AmbiguousMatch(best_id="marie-dupont", best_name="Marie Dupont", score=0.85)


async def test_duplicate_suspect_resolved_true_when_user_confirms():
    """L'utilisateur confirme 'link' explicitement → resolved=True."""
    queue: asyncio.Queue = asyncio.Queue()
    pending: dict[str, ClarificationSlot] = {}
    issues: list[dict] = []
    match = _make_ambiguous_match()
    driver = AsyncMock()

    async def _answer_link():
        await asyncio.sleep(0.01)
        cid = next(iter(pending))
        slot = pending[cid]
        slot.answer = "link"
        slot.event.set()

    with patch("felix.ingest.resolution.add_character_alias", new=AsyncMock()):
        await asyncio.gather(
            _handle_ambiguous_character(
                name="Marie D.",
                context=None,
                match=match,
                char_details={},
                scene_id="scene-001",
                issues=issues,
                queue=queue,
                pending_clarifications=pending,
                char_registry={"marie-dupont": "Marie Dupont"},
                char_aliases={},
                driver=driver,
            ),
            _answer_link(),
        )

    assert len(issues) == 1
    assert issues[0]["type"] == "duplicate_suspect"
    assert issues[0]["resolved"] is True


async def test_duplicate_suspect_resolved_false_on_timeout():
    """Timeout → lien automatique → resolved=False."""
    queue: asyncio.Queue = asyncio.Queue()
    issues: list[dict] = []
    match = _make_ambiguous_match()
    driver = AsyncMock()

    with (
        patch("felix.ingest.resolution.CLARIFICATION_TIMEOUT", 0.01),
        patch("felix.ingest.resolution.add_character_alias", new=AsyncMock()),
    ):
        await _handle_ambiguous_character(
            name="Marie D.",
            context=None,
            match=match,
            char_details={},
            scene_id="scene-001",
            issues=issues,
            queue=queue,
            pending_clarifications={},
            char_registry={"marie-dupont": "Marie Dupont"},
            char_aliases={},
            driver=driver,
        )

    assert len(issues) == 1
    assert issues[0]["type"] == "duplicate_suspect"
    assert issues[0]["resolved"] is False


async def test_location_duplicate_suspect_resolved_true_when_user_confirms():
    """Lieu : utilisateur confirme → resolved=True."""
    from felix.ingest.models import ExtractedLocation, SceneAnalysis as SA

    queue: asyncio.Queue = asyncio.Queue()
    pending: dict[str, ClarificationSlot] = {}
    issues: list[dict] = []
    driver = AsyncMock()

    analysis = SA(
        title="T",
        summary="S",
        era="1940s",
        approximate_date=None,
        characters=[],
        location=ExtractedLocation(name="Planque Lyon", description=None),
        mood=None,
    )
    loc_registry = {"planque-de-lyon": "Planque de Lyon"}

    async def _answer_link():
        await asyncio.sleep(0.01)
        cid = next(iter(pending))
        slot = pending[cid]
        slot.answer = "link"
        slot.event.set()

    with patch("felix.ingest.resolution.add_location_alias", new=AsyncMock()):
        # Patch fuzzy_match_entity pour forcer un AmbiguousMatch
        amb = AmbiguousMatch(best_id="planque-de-lyon", best_name="Planque de Lyon", score=0.86)
        with patch("felix.ingest.resolution.fuzzy_match_entity", return_value=amb):
            await asyncio.gather(
                _resolve_location(
                    analysis=analysis,
                    loc_registry=loc_registry,
                    loc_aliases={},
                    driver=driver,
                    scene_id="scene-001",
                    issues=issues,
                    queue=queue,
                    pending_clarifications=pending,
                ),
                _answer_link(),
            )

    assert len(issues) == 1
    assert issues[0]["type"] == "duplicate_suspect"
    assert issues[0]["resolved"] is True
