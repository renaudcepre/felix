from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from felix.graph import formatters
from felix.graph.repositories.characters import (
    get_character_profile,
    get_character_relations,
    list_all_characters,
)
from felix.graph.repositories.timeline import get_timeline_rows


# --- find_character ---


async def test_find_character_by_name(seeded_driver: AsyncDriver) -> None:
    result = await formatters.find_character(seeded_driver, "Marie Dupont")
    assert "Marie Dupont" in result
    assert "1940s" in result
    assert "Resistance" in result
    assert "Pierre Renard" in result
    assert "spouse" in result


async def test_find_character_partial(seeded_driver: AsyncDriver) -> None:
    result = await formatters.find_character(seeded_driver, "Marie")
    assert "Marie Dupont" in result


async def test_find_character_by_alias(seeded_driver: AsyncDriver) -> None:
    result = await formatters.find_character(seeded_driver, "La Louve")
    assert "Marie Dupont" in result


async def test_find_character_case_insensitive(seeded_driver: AsyncDriver) -> None:
    result = await formatters.find_character(seeded_driver, "marie")
    assert "Marie Dupont" in result


async def test_find_character_no_match(seeded_driver: AsyncDriver) -> None:
    result = await formatters.find_character(seeded_driver, "Napoleon")
    assert "No character" in result
    assert "Marie Dupont" in result
    assert "Pierre Renard" in result


# --- find_location ---


async def test_find_location_by_name(seeded_driver: AsyncDriver) -> None:
    result = await formatters.find_location(seeded_driver, "Lyon")
    assert "Lyon Safe House" in result
    assert "rue Merciere" in result


async def test_find_location_partial(seeded_driver: AsyncDriver) -> None:
    result = await formatters.find_location(seeded_driver, "safe house")
    assert "Lyon Safe House" in result


async def test_find_location_no_match(seeded_driver: AsyncDriver) -> None:
    result = await formatters.find_location(seeded_driver, "Berlin")
    assert "No location" in result
    assert "Lyon Safe House" in result
    assert "Lyon Safe House" in result


# --- get_timeline ---


async def test_get_timeline_filtered_by_date(seeded_driver: AsyncDriver) -> None:
    result = await formatters.get_timeline(
        seeded_driver, date_from="1942-03-01", date_to="1942-03-31"
    )
    assert "Sarah" in result
    assert "1942-03-15" in result


async def test_get_timeline_filtered_by_era(seeded_driver: AsyncDriver) -> None:
    result = await formatters.get_timeline(seeded_driver, era="1970s")
    assert "Julien" in result
    assert "1974" in result
    assert "1942" not in result


async def test_get_timeline_summer_1942(seeded_driver: AsyncDriver) -> None:
    result = await formatters.get_timeline(
        seeded_driver, date_from="1942-06-01", date_to="1942-09-30"
    )
    assert "Benoit passes" in result
    assert "Sarah treats" in result
    assert "Document cache" in result


async def test_get_timeline_no_results(seeded_driver: AsyncDriver) -> None:
    result = await formatters.get_timeline(
        seeded_driver, date_from="2000-01-01", date_to="2000-12-31"
    )
    assert "No timeline events found" in result


async def test_get_timeline_includes_characters(seeded_driver: AsyncDriver) -> None:
    result = await formatters.get_timeline(
        seeded_driver, date_from="1942-06-01", date_to="1942-06-30"
    )
    assert "Benoit Laforge" in result
    assert "Pierre Renard" in result


# --- list_all_characters ---


async def test_list_all_characters(seeded_driver: AsyncDriver) -> None:
    rows = await list_all_characters(seeded_driver)
    assert len(rows) == 5
    names = [r["name"] for r in rows]
    assert "Marie Dupont" in names
    assert "Julien Morel" in names


async def test_list_all_characters_has_era(seeded_driver: AsyncDriver) -> None:
    rows = await list_all_characters(seeded_driver)
    eras = {r["era"] for r in rows}
    assert "1940s" in eras
    assert "1970s" in eras


# --- get_character_profile ---


async def test_get_character_profile(seeded_driver: AsyncDriver) -> None:
    row = await get_character_profile(seeded_driver, "marie-dupont")
    assert row is not None
    assert row["name"] == "Marie Dupont"
    assert row["era"] == "1940s"
    assert row["background"] is not None


async def test_get_character_profile_not_found(seeded_driver: AsyncDriver) -> None:
    row = await get_character_profile(seeded_driver, "nonexistent")
    assert row is None


# --- get_character_relations ---


async def test_get_character_relations(seeded_driver: AsyncDriver) -> None:
    rels = await get_character_relations(seeded_driver, "marie-dupont")
    assert len(rels) == 3
    types = {r["relation_type"] for r in rels}
    assert "spouse" in types
    assert "comrades" in types


async def test_get_character_relations_empty(seeded_driver: AsyncDriver) -> None:
    rels = await get_character_relations(seeded_driver, "nonexistent")
    assert rels == []


# --- get_timeline_rows ---


async def test_get_timeline_rows_all(seeded_driver: AsyncDriver) -> None:
    rows = await get_timeline_rows(seeded_driver)
    assert len(rows) == 10
    assert all(isinstance(r, dict) for r in rows)
    assert "date" in rows[0]
    assert "characters" in rows[0]


async def test_get_timeline_rows_filter_era(seeded_driver: AsyncDriver) -> None:
    rows = await get_timeline_rows(seeded_driver, era="1970s")
    assert len(rows) == 2
    assert all(r["era"] == "1970s" for r in rows)


async def test_get_timeline_rows_has_characters(seeded_driver: AsyncDriver) -> None:
    rows = await get_timeline_rows(
        seeded_driver, date_from="1942-06-01", date_to="1942-06-30"
    )
    assert len(rows) == 1
    assert "Benoit Laforge" in rows[0]["characters"]
