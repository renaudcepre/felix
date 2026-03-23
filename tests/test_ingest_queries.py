from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver

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


async def test_create_and_list_issues(seeded_driver: AsyncDriver) -> None:
    issue = _make_issue()
    await create_issue(seeded_driver, issue)
    rows = await list_issues(seeded_driver)
    assert any(r["id"] == issue["id"] for r in rows)


async def test_list_issues_filter_type(seeded_driver: AsyncDriver) -> None:
    await create_issue(seeded_driver, _make_issue(type="character_contradiction"))
    await create_issue(seeded_driver, _make_issue(type="missing_info"))
    rows = await list_issues(seeded_driver, type="missing_info")
    assert all(r["type"] == "missing_info" for r in rows)


async def test_list_issues_filter_severity(seeded_driver: AsyncDriver) -> None:
    await create_issue(seeded_driver, _make_issue(severity="error"))
    await create_issue(seeded_driver, _make_issue(severity="warning"))
    rows = await list_issues(seeded_driver, severity="error")
    assert all(r["severity"] == "error" for r in rows)


async def test_list_issues_filter_resolved(seeded_driver: AsyncDriver) -> None:
    await create_issue(seeded_driver, _make_issue(resolved=False))
    await create_issue(seeded_driver, _make_issue(resolved=True))
    rows = await list_issues(seeded_driver, resolved=False)
    assert all(r["resolved"] is False for r in rows)


async def test_update_issue_resolved(seeded_driver: AsyncDriver) -> None:
    issue = _make_issue()
    await create_issue(seeded_driver, issue)
    ok = await update_issue_resolved(seeded_driver, issue["id"], True)
    assert ok is True
    rows = await list_issues(seeded_driver, resolved=True)
    assert any(r["id"] == issue["id"] for r in rows)


async def test_update_issue_resolved_not_found(seeded_driver: AsyncDriver) -> None:
    ok = await update_issue_resolved(seeded_driver, "nonexistent", True)
    assert ok is False


async def test_delete_issues_for_scenes(seeded_driver: AsyncDriver) -> None:
    # Need scenes to exist for HAS_ISSUE relationship
    for sid in ("scene-a", "scene-b", "scene-c"):
        async with seeded_driver.session() as session:
            await session.run("MERGE (s:Scene {id: $id}) SET s.filename = $id", id=sid)

    i1 = _make_issue(scene_id="scene-a")
    i2 = _make_issue(scene_id="scene-b")
    i3 = _make_issue(scene_id="scene-c")
    await create_issue(seeded_driver, i1)
    await create_issue(seeded_driver, i2)
    await create_issue(seeded_driver, i3)
    await delete_issues_for_scenes(seeded_driver, ["scene-a", "scene-b"])
    rows = await list_issues(seeded_driver)
    scene_ids = {r.get("scene_id") for r in rows}
    assert "scene-a" not in scene_ids
    assert "scene-b" not in scene_ids
    assert "scene-c" in scene_ids


# --- scenes CRUD ---


async def test_upsert_and_list_scenes(seeded_driver: AsyncDriver) -> None:
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
    await upsert_scene(seeded_driver, scene)
    rows = await list_scenes(seeded_driver)
    assert any(r["id"] == "scene-001" for r in rows)


async def test_upsert_scene_idempotent(seeded_driver: AsyncDriver) -> None:
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
    await upsert_scene(seeded_driver, scene)
    scene["title"] = "Updated"
    await upsert_scene(seeded_driver, scene)
    rows = await list_scenes(seeded_driver)
    matching = [r for r in rows if r["id"] == "scene-002"]
    assert len(matching) == 1
    assert matching[0]["title"] == "Updated"


# --- minimal upserts ---


async def test_upsert_character_minimal_ignore(seeded_driver: AsyncDriver) -> None:
    # marie-dupont already exists from seed — MERGE ON CREATE should not overwrite
    await upsert_character_minimal(
        seeded_driver, {"id": "marie-dupont", "name": "CHANGED", "era": "1940s"}
    )
    row = await get_character_profile(seeded_driver, "marie-dupont")
    assert row is not None
    assert row["name"] == "Marie Dupont"  # NOT changed


async def test_upsert_character_minimal_new(seeded_driver: AsyncDriver) -> None:
    await upsert_character_minimal(
        seeded_driver, {"id": "new-char", "name": "New Char", "era": "1940s"}
    )
    row = await get_character_profile(seeded_driver, "new-char")
    assert row is not None
    assert row["name"] == "New Char"


async def test_upsert_location_minimal_ignore(seeded_driver: AsyncDriver) -> None:
    await upsert_location_minimal(
        seeded_driver, {"id": "lyon-safe-house", "name": "CHANGED", "description": "new"}
    )
    detail = await get_location_detail(seeded_driver, "lyon-safe-house")
    assert detail is not None
    assert detail["name"] == "Planque de Lyon"  # NOT changed


async def test_upsert_timeline_event(seeded_driver: AsyncDriver) -> None:
    evt = {
        "id": "evt-new",
        "date": "1942-04-01",
        "era": "1940s",
        "title": "New event",
        "description": "Something happened",
        "location_id": "lyon-safe-house",
        "scene_id": None,
    }
    await upsert_timeline_event(seeded_driver, evt)
    rows = await get_timeline_rows(seeded_driver, date_from="1942-04-01", date_to="1942-04-01")
    assert len(rows) == 1
    assert rows[0]["title"] == "New event"


async def test_upsert_character_event(seeded_driver: AsyncDriver) -> None:
    evt = {
        "id": "evt-ce-test",
        "date": "1942-04-01",
        "era": "1940s",
        "title": "CE test",
        "description": "",
        "location_id": None,
        "scene_id": None,
    }
    await upsert_timeline_event(seeded_driver, evt)
    await upsert_character_event(seeded_driver, "marie-dupont", "evt-ce-test", "participant")
    rows = await get_timeline_rows(seeded_driver, date_from="1942-04-01", date_to="1942-04-01")
    assert "Marie Dupont" in rows[0]["characters"]
