from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Annotated

from protest import ProTestSuite, Use

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from tests.fixtures import seeded_driver

from felix.graph.repositories.characters import get_character_profile, upsert_character_minimal
from felix.graph.repositories.issues import (
    create_issue,
    delete_issues_for_scenes,
    list_issues,
    update_issue_resolved,
)
from felix.graph.repositories.locations import get_location_detail, upsert_location_minimal
from felix.graph.repositories.scenes import list_scenes, upsert_scene
from felix.graph.repositories.timeline import (
    get_timeline_rows,
    upsert_character_event,
    upsert_timeline_event,
)

ingest_queries_suite = ProTestSuite("IngestQueries")


# --- issues CRUD ---


def _make_issue(**overrides: object) -> dict:
    base = {
        "id": str(uuid.uuid4()),
        "type": "timeline_inconsistency",
        "severity": "warning",
        "scene_id": "scene-test",
        "entity_id": None,
        "description": "Test issue",
        "suggestion": "Fix it",
        "resolved": False,
    }
    base.update(overrides)
    return base


@ingest_queries_suite.test()
async def test_create_and_list_issues(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    issue = _make_issue()
    await create_issue(driver, issue)
    rows = await list_issues(driver)
    assert any(r["id"] == issue["id"] for r in rows)


@ingest_queries_suite.test()
async def test_list_issues_filter_type(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await create_issue(driver, _make_issue(type="character_contradiction"))
    await create_issue(driver, _make_issue(type="missing_info"))
    rows = await list_issues(driver, type="missing_info")
    assert all(r["type"] == "missing_info" for r in rows)


@ingest_queries_suite.test()
async def test_list_issues_filter_severity(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await create_issue(driver, _make_issue(severity="error"))
    await create_issue(driver, _make_issue(severity="warning"))
    rows = await list_issues(driver, severity="error")
    assert all(r["severity"] == "error" for r in rows)


@ingest_queries_suite.test()
async def test_list_issues_filter_resolved(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await create_issue(driver, _make_issue(resolved=False))
    await create_issue(driver, _make_issue(resolved=True))
    rows = await list_issues(driver, resolved=False)
    assert all(r["resolved"] is False for r in rows)


@ingest_queries_suite.test()
async def test_update_issue_resolved(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    issue = _make_issue()
    await create_issue(driver, issue)
    ok = await update_issue_resolved(driver, issue["id"], True)
    assert ok is True
    rows = await list_issues(driver, resolved=True)
    assert any(r["id"] == issue["id"] for r in rows)


@ingest_queries_suite.test()
async def test_update_issue_resolved_not_found(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    ok = await update_issue_resolved(driver, "nonexistent", True)
    assert ok is False


@ingest_queries_suite.test()
async def test_delete_issues_for_scenes(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    # Need scenes to exist for HAS_ISSUE relationship
    for sid in ("scene-a", "scene-b", "scene-c"):
        async with driver.session() as session:
            await session.run("MERGE (s:Scene {id: $id}) SET s.filename = $id", id=sid)

    i1 = _make_issue(scene_id="scene-a")
    i2 = _make_issue(scene_id="scene-b")
    i3 = _make_issue(scene_id="scene-c")
    await create_issue(driver, i1)
    await create_issue(driver, i2)
    await create_issue(driver, i3)
    await delete_issues_for_scenes(driver, ["scene-a", "scene-b"])
    rows = await list_issues(driver)
    scene_ids = {r.get("scene_id") for r in rows}
    assert "scene-a" not in scene_ids
    assert "scene-b" not in scene_ids
    assert "scene-c" in scene_ids


# --- scenes CRUD ---


@ingest_queries_suite.test()
async def test_upsert_and_list_scenes(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    scene = {
        "id": "scene-001",
        "filename": "001.txt",
        "title": "Test scene",
        "summary": "A test",
        "era": "1940s",
        "date": "1942-03-15",
        "location_id": "lyon-safe-house",
        "raw_text": "Full text here",
    }
    await upsert_scene(driver, scene)
    rows = await list_scenes(driver)
    assert any(r["id"] == "scene-001" for r in rows)


@ingest_queries_suite.test()
async def test_upsert_scene_idempotent(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    scene = {
        "id": "scene-002",
        "filename": "002.txt",
        "title": "First",
        "summary": "First summary",
        "era": "1940s",
        "date": "1942-01-01",
        "location_id": None,
        "raw_text": "v1",
    }
    await upsert_scene(driver, scene)
    scene["title"] = "Updated"
    await upsert_scene(driver, scene)
    rows = await list_scenes(driver)
    matching = [r for r in rows if r["id"] == "scene-002"]
    assert len(matching) == 1
    assert matching[0]["title"] == "Updated"


# --- minimal upserts ---


@ingest_queries_suite.test()
async def test_upsert_character_minimal_ignore(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    # marie-dupont already exists from seed — MERGE ON CREATE should not overwrite
    await upsert_character_minimal(
        driver, {"id": "marie-dupont", "name": "CHANGED", "era": "1940s"}
    )
    row = await get_character_profile(driver, "marie-dupont")
    assert row is not None
    assert row["name"] == "Marie Dupont"  # NOT changed


@ingest_queries_suite.test()
async def test_upsert_character_minimal_new(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await upsert_character_minimal(
        driver, {"id": "new-char", "name": "New Char", "era": "1940s"}
    )
    row = await get_character_profile(driver, "new-char")
    assert row is not None
    assert row["name"] == "New Char"


@ingest_queries_suite.test()
async def test_upsert_location_minimal_ignore(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await upsert_location_minimal(
        driver, {"id": "lyon-safe-house", "name": "CHANGED", "description": "new"}
    )
    detail = await get_location_detail(driver, "lyon-safe-house")
    assert detail is not None
    assert detail["name"] == "Lyon Safe House"  # NOT changed


@ingest_queries_suite.test()
async def test_upsert_timeline_event(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    evt = {
        "id": "evt-new",
        "date": "1942-04-01",
        "era": "1940s",
        "title": "New event",
        "description": "Something happened",
        "location_id": "lyon-safe-house",
        "scene_id": None,
    }
    await upsert_timeline_event(driver, evt)
    rows = await get_timeline_rows(driver, date_from="1942-04-01", date_to="1942-04-01")
    assert len(rows) == 1
    assert rows[0]["title"] == "New event"


@ingest_queries_suite.test()
async def test_upsert_character_event(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    evt = {
        "id": "evt-ce-test",
        "date": "1942-04-01",
        "era": "1940s",
        "title": "CE test",
        "description": "",
        "location_id": None,
        "scene_id": None,
    }
    await upsert_timeline_event(driver, evt)
    await upsert_character_event(driver, "marie-dupont", "evt-ce-test", "participant")
    rows = await get_timeline_rows(driver, date_from="1942-04-01", date_to="1942-04-01")
    assert "Marie Dupont" in rows[0]["characters"]
