from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import aiosqlite

from felix.db import queries


@pytest.fixture
async def db(seeded_db: aiosqlite.Connection) -> aiosqlite.Connection:
    return seeded_db


async def test_list_characters_returns_all(db: aiosqlite.Connection) -> None:
    result = await queries.list_characters(db)
    assert "Marie Dupont" in result
    assert "Pierre Renard" in result
    assert "Benoit Laforge" in result
    assert "Sarah Cohen" in result
    assert "Julien Morel" in result


async def test_list_characters_includes_ids(db: aiosqlite.Connection) -> None:
    result = await queries.list_characters(db)
    assert "marie-dupont" in result
    assert "julien-morel" in result


async def test_get_character_found(db: aiosqlite.Connection) -> None:
    result = await queries.get_character(db, "marie-dupont")
    assert "Marie Dupont" in result
    assert "1940s" in result
    assert "Resistance" in result
    assert "La Louve" in result


async def test_get_character_includes_relations(db: aiosqlite.Connection) -> None:
    result = await queries.get_character(db, "marie-dupont")
    assert "Pierre Renard" in result
    assert "spouse" in result


async def test_get_character_not_found(db: aiosqlite.Connection) -> None:
    result = await queries.get_character(db, "unknown-id")
    assert "No character found" in result


async def test_list_locations_returns_all(db: aiosqlite.Connection) -> None:
    result = await queries.list_locations(db)
    assert "Planque de Lyon" in result
    assert "Prefecture de Lyon" in result
    assert "Paris Tribune" in result


async def test_get_location_found(db: aiosqlite.Connection) -> None:
    result = await queries.get_location(db, "lyon-safe-house")
    assert "Planque de Lyon" in result
    assert "rue Merciere" in result


async def test_get_location_not_found(db: aiosqlite.Connection) -> None:
    result = await queries.get_location(db, "unknown-loc")
    assert "No location found" in result


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
