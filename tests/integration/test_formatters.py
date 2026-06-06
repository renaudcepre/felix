from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from protest import ProTestSuite, Use

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from tests.fixtures import seeded_driver

from felix.graph import formatters
from felix.graph.repositories.characters import (
    get_character_profile,
    get_character_relations,
    list_all_characters,
)
from felix.graph.repositories.timeline import get_timeline_rows

formatters_suite = ProTestSuite("Formatters")


# --- find_character ---


@formatters_suite.test()
async def test_find_character_by_name(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await formatters.find_character(driver, "Marie Dupont")
    assert "Marie Dupont" in result
    assert "1940s" in result
    assert "Resistance" in result
    assert "Pierre Renard" in result
    assert "spouse" in result


@formatters_suite.test()
async def test_find_character_partial(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await formatters.find_character(driver, "Marie")
    assert "Marie Dupont" in result


@formatters_suite.test()
async def test_find_character_by_alias(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await formatters.find_character(driver, "La Louve")
    assert "Marie Dupont" in result


@formatters_suite.test()
async def test_find_character_case_insensitive(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await formatters.find_character(driver, "marie")
    assert "Marie Dupont" in result


@formatters_suite.test()
async def test_find_character_no_match(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await formatters.find_character(driver, "Napoleon")
    assert "No character" in result
    assert "Marie Dupont" in result
    assert "Pierre Renard" in result


# --- find_location ---


@formatters_suite.test()
async def test_find_location_by_name(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await formatters.find_location(driver, "Lyon")
    assert "Lyon Safe House" in result
    assert "rue Merciere" in result


@formatters_suite.test()
async def test_find_location_partial(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await formatters.find_location(driver, "safe house")
    assert "Lyon Safe House" in result


@formatters_suite.test()
async def test_find_location_no_match(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await formatters.find_location(driver, "Berlin")
    assert "No location" in result
    assert "Lyon Safe House" in result


# --- get_timeline ---


@formatters_suite.test()
async def test_get_timeline_filtered_by_date(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await formatters.get_timeline(
        driver, date_from="1942-03-01", date_to="1942-03-31"
    )
    assert "Sarah" in result
    assert "1942-03-15" in result


@formatters_suite.test()
async def test_get_timeline_filtered_by_era(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await formatters.get_timeline(driver, era="1970s")
    assert "Julien" in result
    assert "1974" in result
    assert "1942" not in result


@formatters_suite.test()
async def test_get_timeline_summer_1942(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await formatters.get_timeline(
        driver, date_from="1942-06-01", date_to="1942-09-30"
    )
    assert "Benoit passes" in result
    assert "Sarah treats" in result
    assert "Document cache" in result


@formatters_suite.test()
async def test_get_timeline_no_results(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await formatters.get_timeline(
        driver, date_from="2000-01-01", date_to="2000-12-31"
    )
    assert "No timeline events found" in result


@formatters_suite.test()
async def test_get_timeline_includes_characters(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await formatters.get_timeline(
        driver, date_from="1942-06-01", date_to="1942-06-30"
    )
    assert "Benoit Laforge" in result
    assert "Pierre Renard" in result


# --- list_all_characters ---


@formatters_suite.test()
async def test_list_all_characters(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    rows = await list_all_characters(driver)
    assert len(rows) == 5
    names = [r["name"] for r in rows]
    assert "Marie Dupont" in names
    assert "Julien Morel" in names


@formatters_suite.test()
async def test_list_all_characters_has_era(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    rows = await list_all_characters(driver)
    eras = {r["era"] for r in rows}
    assert "1940s" in eras
    assert "1970s" in eras


# --- get_character_profile ---


@formatters_suite.test()
async def test_get_character_profile(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    row = await get_character_profile(driver, "marie-dupont")
    assert row is not None
    assert row["name"] == "Marie Dupont"
    assert row["era"] == "1940s"
    assert row["background"] is not None


@formatters_suite.test()
async def test_get_character_profile_not_found(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    row = await get_character_profile(driver, "nonexistent")
    assert row is None


# --- get_character_relations ---


@formatters_suite.test()
async def test_get_character_relations(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    rels = await get_character_relations(driver, "marie-dupont")
    assert len(rels) == 3
    types = {r["relation_type"] for r in rels}
    assert "spouse" in types
    assert "comrades" in types


@formatters_suite.test()
async def test_get_character_relations_empty(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    rels = await get_character_relations(driver, "nonexistent")
    assert rels == []


# --- get_timeline_rows ---


@formatters_suite.test()
async def test_get_timeline_rows_all(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    rows = await get_timeline_rows(driver)
    assert len(rows) == 10
    assert all(isinstance(r, dict) for r in rows)
    assert "date" in rows[0]
    assert "characters" in rows[0]


@formatters_suite.test()
async def test_get_timeline_rows_filter_era(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    rows = await get_timeline_rows(driver, era="1970s")
    assert len(rows) == 2
    assert all(r["era"] == "1970s" for r in rows)


@formatters_suite.test()
async def test_get_timeline_rows_has_characters(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    rows = await get_timeline_rows(
        driver, date_from="1942-06-01", date_to="1942-06-30"
    )
    assert len(rows) == 1
    assert "Benoit Laforge" in rows[0]["characters"]
