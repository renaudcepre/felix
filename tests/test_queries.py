from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import aiosqlite

from felix.db import queries


@pytest.fixture
async def db(seeded_db: aiosqlite.Connection) -> aiosqlite.Connection:
    return seeded_db


# --- find_character ---


async def test_find_character_by_name(db: aiosqlite.Connection) -> None:
    result = await queries.find_character(db, "Marie Dupont")
    assert "Marie Dupont" in result
    assert "1940s" in result
    assert "Resistance" in result
    assert "Pierre Renard" in result
    assert "spouse" in result


async def test_find_character_partial(db: aiosqlite.Connection) -> None:
    result = await queries.find_character(db, "Marie")
    assert "Marie Dupont" in result


async def test_find_character_by_alias(db: aiosqlite.Connection) -> None:
    result = await queries.find_character(db, "La Louve")
    assert "Marie Dupont" in result


async def test_find_character_case_insensitive(db: aiosqlite.Connection) -> None:
    result = await queries.find_character(db, "marie")
    assert "Marie Dupont" in result


async def test_find_character_no_match(db: aiosqlite.Connection) -> None:
    result = await queries.find_character(db, "Napoleon")
    assert "Aucun personnage" in result
    assert "Marie Dupont" in result
    assert "Pierre Renard" in result


# --- find_location ---


async def test_find_location_by_name(db: aiosqlite.Connection) -> None:
    result = await queries.find_location(db, "Lyon")
    assert "Planque de Lyon" in result
    assert "rue Merciere" in result


async def test_find_location_partial(db: aiosqlite.Connection) -> None:
    result = await queries.find_location(db, "planque")
    assert "Planque de Lyon" in result


async def test_find_location_no_match(db: aiosqlite.Connection) -> None:
    result = await queries.find_location(db, "Berlin")
    assert "Aucun lieu" in result
    assert "Planque de Lyon" in result


# --- get_timeline (unchanged) ---


async def test_get_timeline_filtered_by_date(db: aiosqlite.Connection) -> None:
    result = await queries.get_timeline(
        db, date_from="1942-03-01", date_to="1942-03-31"
    )
    assert "Sarah" in result
    assert "1942-03-15" in result


async def test_get_timeline_filtered_by_era(db: aiosqlite.Connection) -> None:
    result = await queries.get_timeline(db, era="1970s")
    assert "Julien" in result
    assert "1974" in result
    # Should not include 1940s events
    assert "1942" not in result


async def test_get_timeline_summer_1942(db: aiosqlite.Connection) -> None:
    result = await queries.get_timeline(
        db, date_from="1942-06-01", date_to="1942-09-30"
    )
    assert "Benoit transmet" in result
    assert "Sarah soigne" in result
    assert "cache de documents" in result


async def test_get_timeline_no_results(db: aiosqlite.Connection) -> None:
    result = await queries.get_timeline(
        db, date_from="2000-01-01", date_to="2000-12-31"
    )
    assert "No timeline events found" in result


async def test_get_timeline_includes_characters(db: aiosqlite.Connection) -> None:
    result = await queries.get_timeline(
        db, date_from="1942-06-01", date_to="1942-06-30"
    )
    assert "Benoit Laforge" in result
    assert "Pierre Renard" in result
