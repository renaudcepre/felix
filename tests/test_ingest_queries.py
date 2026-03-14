from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import aiosqlite

from felix.db import queries


@pytest.fixture
async def db(seeded_db: aiosqlite.Connection) -> aiosqlite.Connection:
    return seeded_db


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
        "resolved": 0,
    }
    base.update(overrides)
    return base


async def test_create_and_list_issues(db: aiosqlite.Connection) -> None:
    issue = _make_issue()
    await queries.create_issue(db, issue)
    rows = await queries.list_issues(db)
    assert any(r["id"] == issue["id"] for r in rows)


async def test_list_issues_filter_type(db: aiosqlite.Connection) -> None:
    await queries.create_issue(db, _make_issue(type="character_contradiction"))
    await queries.create_issue(db, _make_issue(type="missing_info"))
    rows = await queries.list_issues(db, type="missing_info")
    assert all(r["type"] == "missing_info" for r in rows)


async def test_list_issues_filter_severity(db: aiosqlite.Connection) -> None:
    await queries.create_issue(db, _make_issue(severity="error"))
    await queries.create_issue(db, _make_issue(severity="warning"))
    rows = await queries.list_issues(db, severity="error")
    assert all(r["severity"] == "error" for r in rows)


async def test_list_issues_filter_resolved(db: aiosqlite.Connection) -> None:
    await queries.create_issue(db, _make_issue(resolved=0))
    await queries.create_issue(db, _make_issue(resolved=1))
    rows = await queries.list_issues(db, resolved=False)
    assert all(r["resolved"] == 0 for r in rows)


async def test_update_issue_resolved(db: aiosqlite.Connection) -> None:
    issue = _make_issue()
    await queries.create_issue(db, issue)
    ok = await queries.update_issue_resolved(db, issue["id"], True)
    assert ok is True
    rows = await queries.list_issues(db, resolved=True)
    assert any(r["id"] == issue["id"] for r in rows)


async def test_update_issue_resolved_not_found(db: aiosqlite.Connection) -> None:
    ok = await queries.update_issue_resolved(db, "nonexistent", True)
    assert ok is False


async def test_delete_issues_for_scenes(db: aiosqlite.Connection) -> None:
    i1 = _make_issue(scene_id="scene-a")
    i2 = _make_issue(scene_id="scene-b")
    i3 = _make_issue(scene_id="scene-c")
    await queries.create_issue(db, i1)
    await queries.create_issue(db, i2)
    await queries.create_issue(db, i3)
    await queries.delete_issues_for_scenes(db, ["scene-a", "scene-b"])
    rows = await queries.list_issues(db)
    scene_ids = {r["scene_id"] for r in rows}
    assert "scene-a" not in scene_ids
    assert "scene-b" not in scene_ids
    assert "scene-c" in scene_ids


# --- scenes CRUD ---


async def test_upsert_and_list_scenes(db: aiosqlite.Connection) -> None:
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
    await queries.upsert_scene(db, scene)
    rows = await queries.list_scenes(db)
    assert any(r["id"] == "scene-001" for r in rows)


async def test_upsert_scene_idempotent(db: aiosqlite.Connection) -> None:
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
    await queries.upsert_scene(db, scene)
    scene["title"] = "Updated"
    await queries.upsert_scene(db, scene)
    rows = await queries.list_scenes(db)
    matching = [r for r in rows if r["id"] == "scene-002"]
    assert len(matching) == 1
    assert matching[0]["title"] == "Updated"


# --- minimal upserts ---


async def test_upsert_character_minimal_ignore(db: aiosqlite.Connection) -> None:
    # marie-dupont already exists from seed
    await queries.upsert_character_minimal(
        db, {"id": "marie-dupont", "name": "CHANGED", "era": "1940s"}
    )
    row = await queries.get_character_profile(db, "marie-dupont")
    assert row is not None
    assert row["name"] == "Marie Dupont"  # NOT changed


async def test_upsert_character_minimal_new(db: aiosqlite.Connection) -> None:
    await queries.upsert_character_minimal(
        db, {"id": "new-char", "name": "New Char", "era": "1940s"}
    )
    row = await queries.get_character_profile(db, "new-char")
    assert row is not None
    assert row["name"] == "New Char"


async def test_upsert_location_minimal_ignore(db: aiosqlite.Connection) -> None:
    await queries.upsert_location_minimal(
        db, {"id": "lyon-safe-house", "name": "CHANGED", "description": "new"}
    )
    result = await queries.find_location(db, "Planque de Lyon")
    assert "Planque de Lyon" in result  # NOT changed


async def test_upsert_timeline_event(db: aiosqlite.Connection) -> None:
    evt = {
        "id": "evt-new",
        "date": "1942-04-01",
        "era": "1940s",
        "title": "New event",
        "description": "Something happened",
        "location_id": "lyon-safe-house",
        "scene_id": "scene-001",
    }
    await queries.upsert_timeline_event(db, evt)
    rows = await queries.get_timeline_rows(db, date_from="1942-04-01", date_to="1942-04-01")
    assert len(rows) == 1
    assert rows[0]["title"] == "New event"


async def test_upsert_character_event(db: aiosqlite.Connection) -> None:
    evt = {
        "id": "evt-ce-test",
        "date": "1942-04-01",
        "era": "1940s",
        "title": "CE test",
        "description": "",
        "location_id": None,
        "scene_id": None,
    }
    await queries.upsert_timeline_event(db, evt)
    await queries.upsert_character_event(db, "marie-dupont", "evt-ce-test", "participant")
    rows = await queries.get_timeline_rows(db, date_from="1942-04-01", date_to="1942-04-01")
    assert "Marie Dupont" in rows[0]["characters"]
