from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from unittest.mock import AsyncMock, MagicMock

from protest import ProTestSuite, Use

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from tests.fixtures import seeded_driver
from tests.integration.helpers import get_char, insert_character

from felix.graph.repositories.characters import patch_character_profile_fields
from felix.graph.repositories.scenes import get_scene_summaries_by_ids, upsert_scene
from felix.ingest.models import CharacterProfile
from felix.ingest.profiler import patch_character_profile

profiler_suite = ProTestSuite("ProfilerAndRepository")


# ---------------------------------------------------------------------------
# get_scene_summaries_by_ids
# ---------------------------------------------------------------------------


@profiler_suite.test()
async def test_get_scene_summaries_empty(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await get_scene_summaries_by_ids(driver, [])
    assert result == []


@profiler_suite.test()
async def test_get_scene_summaries_unknown_ids(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await get_scene_summaries_by_ids(driver, ["scene-does-not-exist"])
    assert result == []


@profiler_suite.test()
async def test_get_scene_summaries_returns_inserted(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await upsert_scene(driver, {
        "id": "scene-001", "filename": "001.txt", "title": "Le signal",
        "summary": "Une technicienne recoit un signal.", "era": "2030s",
        "date": "2031-04-01", "location_id": None, "raw_text": "",
    })
    await upsert_scene(driver, {
        "id": "scene-002", "filename": "002.txt", "title": "L'intrusion",
        "summary": "Un inconnu entre dans la base.", "era": "2030s",
        "date": "2031-04-02", "location_id": None, "raw_text": "",
    })

    result = await get_scene_summaries_by_ids(driver, ["scene-001", "scene-002"])
    assert len(result) == 2
    ids = {r["id"] for r in result}
    assert ids == {"scene-001", "scene-002"}
    titles = {r["title"] for r in result}
    assert "Le signal" in titles
    assert "L'intrusion" in titles


@profiler_suite.test()
async def test_get_scene_summaries_partial_match(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await upsert_scene(driver, {
        "id": "scene-010", "filename": "010.txt", "title": "La fuite",
        "summary": "Ils fuient.", "era": "1940s", "date": "1942-01-01",
        "location_id": None, "raw_text": "",
    })

    result = await get_scene_summaries_by_ids(driver, ["scene-010", "scene-999"])
    assert len(result) == 1
    assert result[0]["id"] == "scene-010"


@profiler_suite.test()
async def test_get_scene_summaries_returns_correct_fields(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await upsert_scene(driver, {
        "id": "scene-020", "filename": "020.txt", "title": "La reunion",
        "summary": "Une reunion secrete.", "era": "1940s", "date": "1943-06-06",
        "location_id": "lyon-safe-house", "raw_text": "",
    })

    result = await get_scene_summaries_by_ids(driver, ["scene-020"])
    assert len(result) == 1
    row = result[0]
    assert "id" in row
    assert "title" in row
    assert "summary" in row
    assert "era" in row
    assert "date" in row
    assert "location_id" in row
    assert row["title"] == "La reunion"
    assert row["era"] == "1940s"
    assert row["date"] == "1943-06-06"
    assert row["location_id"] == "lyon-safe-house"


# ---------------------------------------------------------------------------
# patch_character_profile_fields (DB)
# ---------------------------------------------------------------------------


@profiler_suite.test()
async def test_patch_concatenates_background(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await insert_character(driver, "clara", background="Signal recu en avril")
    await patch_character_profile_fields(driver, "clara", {"background": "Transferee depuis Kepler-9"})
    row = await get_char(driver, "clara")
    assert "Signal recu en avril" in row["background"]
    assert "Transferee depuis Kepler-9" in row["background"]


@profiler_suite.test()
async def test_patch_concatenates_arc(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await insert_character(driver, "clara", arc="Decouvre le signal")
    await patch_character_profile_fields(driver, "clara", {"arc": "Alerte les collegues"})
    row = await get_char(driver, "clara")
    assert "Decouvre le signal" in row["arc"]
    assert "Alerte les collegues" in row["arc"]


@profiler_suite.test()
async def test_patch_null_preserves_existing(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await insert_character(driver, "clara", background="Donnee initiale", arc="Arc initial")
    await patch_character_profile_fields(driver, "clara", {"background": None, "arc": None})
    row = await get_char(driver, "clara")
    assert row["background"] == "Donnee initiale"
    assert row["arc"] == "Arc initial"


@profiler_suite.test()
async def test_patch_fills_null_field(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await insert_character(driver, "clara")
    await patch_character_profile_fields(driver, "clara", {"background": "Nouveau background"})
    row = await get_char(driver, "clara")
    assert row["background"] == "Nouveau background"


@profiler_suite.test()
async def test_patch_empty_string_treated_as_null(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    """Empty strings from LLM should not pollute existing data."""
    await insert_character(driver, "clara", background="Signal recu en avril", arc="Decouvre le signal")
    await patch_character_profile_fields(driver, "clara", {"background": "", "arc": "  ", "traits": ""})
    row = await get_char(driver, "clara")
    assert row["background"] == "Signal recu en avril"
    assert row["arc"] == "Decouvre le signal"
    assert row.get("traits") is None


@profiler_suite.test()
async def test_patch_age_overwrites(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    """age uses overwrite (not concatenation)."""
    await insert_character(driver, "clara", age="30 ans")
    await patch_character_profile_fields(driver, "clara", {"age": "31 ans"})
    row = await get_char(driver, "clara")
    assert row["age"] == "31 ans"


# ---------------------------------------------------------------------------
# patch_character_profile (agent) — no DB needed
# ---------------------------------------------------------------------------


def _make_agent(profile: CharacterProfile) -> MagicMock:
    result = MagicMock()
    result.output = profile
    agent = MagicMock()
    agent.run = AsyncMock(return_value=result)
    return agent


EXISTING_PROFILE = {
    "age": "30 ans",
    "physical": "Cheveux noirs",
    "background": None,
    "arc": "Cherche des reponses",
    "traits": "Determinee",
}

PATCH_RESULT = CharacterProfile(
    age=None,
    physical=None,
    background="Ingenieure spatiale depuis 2025",
    arc=None,
    traits=None,
)


@profiler_suite.test()
async def test_patch_character_profile_returns_agent_output() -> None:
    agent = _make_agent(PATCH_RESULT)
    result = await patch_character_profile(
        agent,
        name="Clara",
        existing_profile=EXISTING_PROFILE,
        new_scene_text="Clara parle de son parcours d'ingenieure.",
        new_scene_fragment={"scene_id": "scene-005", "role": "participant", "description": "Clara explique son passe."},
    )
    assert result is PATCH_RESULT
    agent.run.assert_awaited_once()


@profiler_suite.test()
async def test_patch_character_profile_input_contains_name() -> None:
    agent = _make_agent(PATCH_RESULT)
    await patch_character_profile(
        agent,
        name="Clara",
        existing_profile=EXISTING_PROFILE,
        new_scene_text="Texte de la scene.",
        new_scene_fragment={"scene_id": "scene-005", "role": "participant", "description": ""},
    )
    input_text: str = agent.run.call_args[0][0]
    assert "Clara" in input_text


@profiler_suite.test()
async def test_patch_character_profile_input_contains_existing_fields() -> None:
    agent = _make_agent(PATCH_RESULT)
    await patch_character_profile(
        agent,
        name="Clara",
        existing_profile=EXISTING_PROFILE,
        new_scene_text="Texte de la scene.",
        new_scene_fragment={"scene_id": "scene-005", "role": "participant", "description": ""},
    )
    input_text: str = agent.run.call_args[0][0]
    assert "30 ans" in input_text
    assert "Cheveux noirs" in input_text
    assert "Determinee" in input_text


@profiler_suite.test()
async def test_patch_character_profile_input_contains_scene_text() -> None:
    agent = _make_agent(PATCH_RESULT)
    scene_text = "Elle decrit son parcours d'ingenieure spatiale avec precision."
    await patch_character_profile(
        agent,
        name="Clara",
        existing_profile=EXISTING_PROFILE,
        new_scene_text=scene_text,
        new_scene_fragment={"scene_id": "scene-005", "role": "participant", "description": ""},
    )
    input_text: str = agent.run.call_args[0][0]
    assert scene_text in input_text


@profiler_suite.test()
async def test_patch_character_profile_uses_scene_title_over_id() -> None:
    agent = _make_agent(PATCH_RESULT)
    await patch_character_profile(
        agent,
        name="Clara",
        existing_profile=EXISTING_PROFILE,
        new_scene_text="Texte.",
        new_scene_fragment={
            "scene_id": "scene-005",
            "scene_title": "Le laboratoire",
            "role": "participant",
            "description": "",
        },
    )
    input_text: str = agent.run.call_args[0][0]
    assert "Le laboratoire" in input_text
    assert "scene-005" not in input_text


@profiler_suite.test()
async def test_patch_character_profile_falls_back_to_scene_id() -> None:
    agent = _make_agent(PATCH_RESULT)
    await patch_character_profile(
        agent,
        name="Clara",
        existing_profile=EXISTING_PROFILE,
        new_scene_text="Texte.",
        new_scene_fragment={"scene_id": "scene-007", "role": "participant", "description": ""},
    )
    input_text: str = agent.run.call_args[0][0]
    assert "scene-007" in input_text
