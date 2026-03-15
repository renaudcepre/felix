from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    import aiosqlite

from felix.db.repository import get_scene_summaries_by_ids
from felix.db.schema import init_db
from felix.ingest.models import CharacterProfile
from felix.ingest.profiler import patch_character_profile


@pytest.fixture
async def db() -> aiosqlite.Connection:
    conn = await init_db(":memory:")
    yield conn  # type: ignore[misc]
    await conn.close()


# ---------------------------------------------------------------------------
# get_scene_summaries_by_ids
# ---------------------------------------------------------------------------


async def test_get_scene_summaries_empty(db: aiosqlite.Connection) -> None:
    result = await get_scene_summaries_by_ids(db, [])
    assert result == []


async def test_get_scene_summaries_unknown_ids(db: aiosqlite.Connection) -> None:
    result = await get_scene_summaries_by_ids(db, ["scene-does-not-exist"])
    assert result == []


async def test_get_scene_summaries_returns_inserted(db: aiosqlite.Connection) -> None:
    await db.execute(
        "INSERT INTO scenes (id, filename, title, summary, era, date, location_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("scene-001", "001.txt", "Le signal", "Une technicienne recoit un signal.", "2030s", "2031-04-01", None),
    )
    await db.execute(
        "INSERT INTO scenes (id, filename, title, summary, era, date, location_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("scene-002", "002.txt", "L'intrusion", "Un inconnu entre dans la base.", "2030s", "2031-04-02", None),
    )
    await db.commit()

    result = await get_scene_summaries_by_ids(db, ["scene-001", "scene-002"])
    assert len(result) == 2
    ids = {r["id"] for r in result}
    assert ids == {"scene-001", "scene-002"}
    titles = {r["title"] for r in result}
    assert "Le signal" in titles
    assert "L'intrusion" in titles


async def test_get_scene_summaries_partial_match(db: aiosqlite.Connection) -> None:
    await db.execute(
        "INSERT INTO scenes (id, filename, title, summary, era, date, location_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("scene-010", "010.txt", "La fuite", "Ils fuient.", "1940s", "1942-01-01", None),
    )
    await db.commit()

    result = await get_scene_summaries_by_ids(db, ["scene-010", "scene-999"])
    assert len(result) == 1
    assert result[0]["id"] == "scene-010"


async def test_get_scene_summaries_returns_correct_fields(db: aiosqlite.Connection) -> None:
    await db.execute(
        "INSERT INTO scenes (id, filename, title, summary, era, date, location_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("scene-020", "020.txt", "La reunion", "Une reunion secrete.", "1940s", "1943-06-06", "loc-1"),
    )
    await db.commit()

    result = await get_scene_summaries_by_ids(db, ["scene-020"])
    assert len(result) == 1
    row = result[0]
    assert set(row.keys()) == {"id", "title", "summary", "era", "date", "location_id"}
    assert row["title"] == "La reunion"
    assert row["era"] == "1940s"
    assert row["date"] == "1943-06-06"
    assert row["location_id"] == "loc-1"


# ---------------------------------------------------------------------------
# patch_character_profile
# ---------------------------------------------------------------------------


def _make_agent(profile: CharacterProfile) -> MagicMock:
    """Agent mock dont agent.run() retourne result.output = profile."""
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
    # background est None : ne doit pas apparaitre
    assert "background" not in input_text or "None" not in input_text


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
    # L'id brut ne doit pas apparaitre si le titre est present
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
