from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from felix.graph.repository import get_scene_summaries_by_ids, patch_character_profile_fields, upsert_scene
from felix.ingest.models import CharacterProfile
from felix.ingest.profiler import patch_character_profile


@pytest.fixture
async def driver_with_scene(seeded_driver: AsyncDriver) -> AsyncDriver:
    """seeded_driver with a few test scenes inserted."""
    return seeded_driver


# ---------------------------------------------------------------------------
# get_scene_summaries_by_ids
# ---------------------------------------------------------------------------


async def test_get_scene_summaries_empty(seeded_driver: AsyncDriver) -> None:
    result = await get_scene_summaries_by_ids(seeded_driver, [])
    assert result == []


async def test_get_scene_summaries_unknown_ids(seeded_driver: AsyncDriver) -> None:
    result = await get_scene_summaries_by_ids(seeded_driver, ["scene-does-not-exist"])
    assert result == []


async def test_get_scene_summaries_returns_inserted(seeded_driver: AsyncDriver) -> None:
    await upsert_scene(seeded_driver, {
        "id": "scene-001", "filename": "001.txt", "title": "Le signal",
        "summary": "Une technicienne recoit un signal.", "era": "2030s",
        "date": "2031-04-01", "location_id": None, "raw_text": "",
    })
    await upsert_scene(seeded_driver, {
        "id": "scene-002", "filename": "002.txt", "title": "L'intrusion",
        "summary": "Un inconnu entre dans la base.", "era": "2030s",
        "date": "2031-04-02", "location_id": None, "raw_text": "",
    })

    result = await get_scene_summaries_by_ids(seeded_driver, ["scene-001", "scene-002"])
    assert len(result) == 2
    ids = {r["id"] for r in result}
    assert ids == {"scene-001", "scene-002"}
    titles = {r["title"] for r in result}
    assert "Le signal" in titles
    assert "L'intrusion" in titles


async def test_get_scene_summaries_partial_match(seeded_driver: AsyncDriver) -> None:
    await upsert_scene(seeded_driver, {
        "id": "scene-010", "filename": "010.txt", "title": "La fuite",
        "summary": "Ils fuient.", "era": "1940s", "date": "1942-01-01",
        "location_id": None, "raw_text": "",
    })

    result = await get_scene_summaries_by_ids(seeded_driver, ["scene-010", "scene-999"])
    assert len(result) == 1
    assert result[0]["id"] == "scene-010"


async def test_get_scene_summaries_returns_correct_fields(seeded_driver: AsyncDriver) -> None:
    await upsert_scene(seeded_driver, {
        "id": "scene-020", "filename": "020.txt", "title": "La reunion",
        "summary": "Une reunion secrete.", "era": "1940s", "date": "1943-06-06",
        "location_id": "lyon-safe-house", "raw_text": "",
    })

    result = await get_scene_summaries_by_ids(seeded_driver, ["scene-020"])
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


async def _insert_character(driver: AsyncDriver, char_id: str, **fields) -> None:
    props = {"id": char_id, "name": char_id, "era": "2030s", **fields}
    set_clauses = ", ".join(f"c.{k} = ${k}" for k in props if k != "id")
    async with driver.session() as session:
        await session.run(
            f"MERGE (c:Character {{id: $id}}) SET {set_clauses}",
            **props,
        )


async def _get_char(driver: AsyncDriver, char_id: str) -> dict:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Character {id: $id}) RETURN c", id=char_id
        )
        record = await result.single()
        return dict(record["c"]) if record else {}


async def test_patch_concatenates_background(seeded_driver: AsyncDriver) -> None:
    await _insert_character(seeded_driver, "clara", background="Signal recu en avril")
    await patch_character_profile_fields(seeded_driver, "clara", {"background": "Transferee depuis Kepler-9"})
    row = await _get_char(seeded_driver, "clara")
    assert "Signal recu en avril" in row["background"]
    assert "Transferee depuis Kepler-9" in row["background"]


async def test_patch_concatenates_arc(seeded_driver: AsyncDriver) -> None:
    await _insert_character(seeded_driver, "clara", arc="Decouvre le signal")
    await patch_character_profile_fields(seeded_driver, "clara", {"arc": "Alerte les collegues"})
    row = await _get_char(seeded_driver, "clara")
    assert "Decouvre le signal" in row["arc"]
    assert "Alerte les collegues" in row["arc"]


async def test_patch_null_preserves_existing(seeded_driver: AsyncDriver) -> None:
    await _insert_character(seeded_driver, "clara", background="Donnee initiale", arc="Arc initial")
    await patch_character_profile_fields(seeded_driver, "clara", {"background": None, "arc": None})
    row = await _get_char(seeded_driver, "clara")
    assert row["background"] == "Donnee initiale"
    assert row["arc"] == "Arc initial"


async def test_patch_fills_null_field(seeded_driver: AsyncDriver) -> None:
    await _insert_character(seeded_driver, "clara")
    await patch_character_profile_fields(seeded_driver, "clara", {"background": "Nouveau background"})
    row = await _get_char(seeded_driver, "clara")
    assert row["background"] == "Nouveau background"


async def test_patch_empty_string_treated_as_null(seeded_driver: AsyncDriver) -> None:
    """Empty strings from LLM should not pollute existing data."""
    await _insert_character(seeded_driver, "clara", background="Signal recu en avril", arc="Decouvre le signal")
    await patch_character_profile_fields(seeded_driver, "clara", {"background": "", "arc": "  ", "traits": ""})
    row = await _get_char(seeded_driver, "clara")
    assert row["background"] == "Signal recu en avril"
    assert row["arc"] == "Decouvre le signal"
    assert row.get("traits") is None


async def test_patch_age_overwrites(seeded_driver: AsyncDriver) -> None:
    """age uses overwrite (not concatenation)."""
    await _insert_character(seeded_driver, "clara", age="30 ans")
    await patch_character_profile_fields(seeded_driver, "clara", {"age": "31 ans"})
    row = await _get_char(seeded_driver, "clara")
    assert row["age"] == "31 ans"


# ---------------------------------------------------------------------------
# patch_character_profile (agent)
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
