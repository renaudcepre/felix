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


# --- list_all_characters ---


async def test_list_all_characters(db: aiosqlite.Connection) -> None:
    rows = await queries.list_all_characters(db)
    assert len(rows) == 5
    names = [r["name"] for r in rows]
    assert "Marie Dupont" in names
    assert "Julien Morel" in names


async def test_list_all_characters_has_era(db: aiosqlite.Connection) -> None:
    rows = await queries.list_all_characters(db)
    eras = {r["era"] for r in rows}
    assert "1940s" in eras
    assert "1970s" in eras


# --- get_character_profile ---


async def test_get_character_profile(db: aiosqlite.Connection) -> None:
    row = await queries.get_character_profile(db, "marie-dupont")
    assert row is not None
    assert row["name"] == "Marie Dupont"
    assert row["era"] == "1940s"
    assert row["background"] is not None


async def test_get_character_profile_not_found(db: aiosqlite.Connection) -> None:
    row = await queries.get_character_profile(db, "nonexistent")
    assert row is None


# --- get_character_relations ---


async def test_get_character_relations(db: aiosqlite.Connection) -> None:
    rels = await queries.get_character_relations(db, "marie-dupont")
    assert len(rels) == 3
    types = {r["relation_type"] for r in rels}
    assert "spouse" in types
    assert "comrades" in types


async def test_get_character_relations_empty(db: aiosqlite.Connection) -> None:
    rels = await queries.get_character_relations(db, "nonexistent")
    assert rels == []


# --- get_timeline_rows ---


async def test_get_timeline_rows_all(db: aiosqlite.Connection) -> None:
    rows = await queries.get_timeline_rows(db)
    assert len(rows) == 10
    assert all(isinstance(r, dict) for r in rows)
    assert "date" in rows[0]
    assert "characters" in rows[0]


async def test_get_timeline_rows_filter_era(db: aiosqlite.Connection) -> None:
    rows = await queries.get_timeline_rows(db, era="1970s")
    assert len(rows) == 2
    assert all(r["era"] == "1970s" for r in rows)


async def test_get_timeline_rows_has_characters(db: aiosqlite.Connection) -> None:
    rows = await queries.get_timeline_rows(
        db, date_from="1942-06-01", date_to="1942-06-30"
    )
    assert len(rows) == 1
    assert "Benoit Laforge" in rows[0]["characters"]
