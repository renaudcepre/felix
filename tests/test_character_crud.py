from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

from unittest.mock import AsyncMock, patch

from felix.api.deps import get_base_url, get_driver, get_model_name
from felix.api.routes.characters import router
from felix.graph.repositories.characters import (
    delete_character_relation,
    overwrite_character_profile_fields,
    upsert_character_relation,
)
from felix.ingest.models import ConsistencyIssue, ConsistencyReport


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_profiler_and_repository.py)
# ---------------------------------------------------------------------------


async def _insert_character(driver: AsyncDriver, char_id: str, **fields: object) -> None:
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


async def _insert_relation(
    driver: AsyncDriver,
    a: str,
    b: str,
    relation_type: str,
    description: str | None = None,
) -> None:
    await upsert_character_relation(driver, a, b, relation_type, description=description)


# ---------------------------------------------------------------------------
# Repository tests: overwrite_character_profile_fields
# ---------------------------------------------------------------------------


async def test_overwrite_replaces_background(seeded_driver: AsyncDriver) -> None:
    await _insert_character(seeded_driver, "clara", background="Signal recu en avril")
    await overwrite_character_profile_fields(seeded_driver, "clara", {"background": "Nouvelle bio"})
    row = await _get_char(seeded_driver, "clara")
    assert row["background"] == "Nouvelle bio"


async def test_overwrite_replaces_arc(seeded_driver: AsyncDriver) -> None:
    await _insert_character(seeded_driver, "clara", arc="Decouvre le signal")
    await overwrite_character_profile_fields(seeded_driver, "clara", {"arc": "Nouvel arc"})
    row = await _get_char(seeded_driver, "clara")
    assert row["arc"] == "Nouvel arc"


async def test_overwrite_clears_field_with_null(seeded_driver: AsyncDriver) -> None:
    await _insert_character(seeded_driver, "clara", age="30 ans", physical="Grande")
    await overwrite_character_profile_fields(seeded_driver, "clara", {"age": None})
    row = await _get_char(seeded_driver, "clara")
    assert row.get("age") is None
    assert row["physical"] == "Grande"


async def test_overwrite_partial_update(seeded_driver: AsyncDriver) -> None:
    await _insert_character(seeded_driver, "clara", age="30 ans", traits="Curieuse")
    await overwrite_character_profile_fields(seeded_driver, "clara", {"age": "31 ans"})
    row = await _get_char(seeded_driver, "clara")
    assert row["age"] == "31 ans"
    assert row["traits"] == "Curieuse"


async def test_overwrite_returns_false_for_unknown_char(seeded_driver: AsyncDriver) -> None:
    result = await overwrite_character_profile_fields(seeded_driver, "inconnu", {"age": "20"})
    assert result is False


async def test_overwrite_empty_dict_is_noop(seeded_driver: AsyncDriver) -> None:
    await _insert_character(seeded_driver, "clara", age="30 ans")
    result = await overwrite_character_profile_fields(seeded_driver, "clara", {})
    assert result is True
    row = await _get_char(seeded_driver, "clara")
    assert row["age"] == "30 ans"


# ---------------------------------------------------------------------------
# Repository tests: delete_character_relation
# ---------------------------------------------------------------------------


async def test_delete_relation_removes_edge(seeded_driver: AsyncDriver) -> None:
    await _insert_character(seeded_driver, "alice")
    await _insert_character(seeded_driver, "bob")
    await _insert_relation(seeded_driver, "alice", "bob", "allie")
    result = await delete_character_relation(seeded_driver, "alice", "bob", "allie")
    assert result is True


async def test_delete_relation_returns_false_if_not_found(seeded_driver: AsyncDriver) -> None:
    await _insert_character(seeded_driver, "alice")
    await _insert_character(seeded_driver, "bob")
    result = await delete_character_relation(seeded_driver, "alice", "bob", "ennemi")
    assert result is False


async def test_delete_relation_keeps_other_relations(seeded_driver: AsyncDriver) -> None:
    await _insert_character(seeded_driver, "alice")
    await _insert_character(seeded_driver, "bob")
    await _insert_relation(seeded_driver, "alice", "bob", "allie")
    await _insert_relation(seeded_driver, "alice", "bob", "collegue")
    await delete_character_relation(seeded_driver, "alice", "bob", "allie")
    # collegue should still exist
    from felix.graph.repositories.characters import get_relation_types_for_pair

    types = await get_relation_types_for_pair(seeded_driver, "alice", "bob")
    assert "collegue" in types
    assert "allie" not in types


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(seeded_driver: AsyncDriver) -> AsyncGenerator[AsyncClient]:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_driver] = lambda: seeded_driver
    app.dependency_overrides[get_model_name] = lambda: "test-model"
    app.dependency_overrides[get_base_url] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# --- POST /api/characters ---


async def test_post_character_201(client: AsyncClient) -> None:
    resp = await client.post("/api/characters", json={"name": "Clara Voss", "era": "2030s"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Clara Voss"
    assert data["era"] == "2030s"
    assert data["id"] == "clara-voss"


async def test_post_character_409_duplicate(seeded_driver: AsyncDriver, client: AsyncClient) -> None:
    await _insert_character(seeded_driver, "clara-voss", name="Clara Voss")
    resp = await client.post("/api/characters", json={"name": "Clara Voss", "era": "2030s"})
    assert resp.status_code == 409


async def test_post_character_422_missing_fields(client: AsyncClient) -> None:
    resp = await client.post("/api/characters", json={"name": "Clara"})
    assert resp.status_code == 422


# --- PATCH /api/characters/{char_id} ---


async def test_patch_character_200(seeded_driver: AsyncDriver, client: AsyncClient) -> None:
    await _insert_character(seeded_driver, "clara", age="30 ans")
    resp = await client.patch("/api/characters/clara", json={"age": "31 ans"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["age"] == "31 ans"
    assert data["id"] == "clara"


async def test_patch_character_partial(seeded_driver: AsyncDriver, client: AsyncClient) -> None:
    await _insert_character(seeded_driver, "clara", age="30 ans", traits="Curieuse")
    resp = await client.patch("/api/characters/clara", json={"age": "31 ans"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["age"] == "31 ans"
    assert data["traits"] == "Curieuse"


async def test_patch_character_clear_field(seeded_driver: AsyncDriver, client: AsyncClient) -> None:
    await _insert_character(seeded_driver, "clara", age="30 ans")
    resp = await client.patch("/api/characters/clara", json={"age": None})
    assert resp.status_code == 200
    assert resp.json()["age"] is None


async def test_patch_character_404(client: AsyncClient) -> None:
    resp = await client.patch("/api/characters/inconnu", json={"age": "20"})
    assert resp.status_code == 404


async def test_patch_character_empty_body(seeded_driver: AsyncDriver, client: AsyncClient) -> None:
    await _insert_character(seeded_driver, "clara", age="30 ans")
    resp = await client.patch("/api/characters/clara", json={})
    assert resp.status_code == 200
    assert resp.json()["age"] == "30 ans"


# --- PUT /api/characters/{a}/relations/{b} ---


async def test_put_relation_creates(seeded_driver: AsyncDriver, client: AsyncClient) -> None:
    await _insert_character(seeded_driver, "alice")
    await _insert_character(seeded_driver, "bob")
    resp = await client.put(
        "/api/characters/alice/relations/bob",
        json={"relation_type": "frere", "description": "Jumeaux"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["relation_type"] == "frere"
    assert data["other_name"] == "bob"


async def test_put_relation_updates(seeded_driver: AsyncDriver, client: AsyncClient) -> None:
    await _insert_character(seeded_driver, "alice")
    await _insert_character(seeded_driver, "bob")
    await _insert_relation(seeded_driver, "alice", "bob", "allie", description="Ancienne")
    resp = await client.put(
        "/api/characters/alice/relations/bob",
        json={"relation_type": "allie", "description": "Renforcee"},
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Renforcee"


async def test_put_relation_404_unknown_char(seeded_driver: AsyncDriver, client: AsyncClient) -> None:
    await _insert_character(seeded_driver, "alice")
    resp = await client.put(
        "/api/characters/alice/relations/inconnu",
        json={"relation_type": "frere"},
    )
    assert resp.status_code == 404


# --- DELETE /api/characters/{a}/relations/{b} ---


async def test_delete_relation_204(seeded_driver: AsyncDriver, client: AsyncClient) -> None:
    await _insert_character(seeded_driver, "alice")
    await _insert_character(seeded_driver, "bob")
    await _insert_relation(seeded_driver, "alice", "bob", "allie")
    resp = await client.delete(
        "/api/characters/alice/relations/bob?relation_type=allie"
    )
    assert resp.status_code == 204


async def test_delete_relation_404(seeded_driver: AsyncDriver, client: AsyncClient) -> None:
    await _insert_character(seeded_driver, "alice")
    await _insert_character(seeded_driver, "bob")
    resp = await client.delete(
        "/api/characters/alice/relations/bob?relation_type=ennemi"
    )
    assert resp.status_code == 404


async def test_delete_relation_requires_type(seeded_driver: AsyncDriver, client: AsyncClient) -> None:
    await _insert_character(seeded_driver, "alice")
    await _insert_character(seeded_driver, "bob")
    resp = await client.delete("/api/characters/alice/relations/bob")
    assert resp.status_code == 422


# --- POST /api/characters/{char_id}/check-consistency ---


async def test_check_consistency_404(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/characters/inconnu/check-consistency", json={"age": "20"}
    )
    assert resp.status_code == 404


async def test_check_consistency_empty_body(
    seeded_driver: AsyncDriver, client: AsyncClient
) -> None:
    await _insert_character(seeded_driver, "clara", age="30 ans")
    resp = await client.post("/api/characters/clara/check-consistency", json={})
    assert resp.status_code == 200
    assert resp.json()["issues"] == []


@patch("felix.api.routes.characters.check_character_consistency")
async def test_check_consistency_calls_agent(
    mock_check: AsyncMock, seeded_driver: AsyncDriver, client: AsyncClient
) -> None:
    await _insert_character(seeded_driver, "clara", age="30 ans")
    mock_check.return_value = ConsistencyReport(issues=[])

    resp = await client.post(
        "/api/characters/clara/check-consistency", json={"age": "25 ans"}
    )
    assert resp.status_code == 200

    mock_check.assert_called_once()
    call_kwargs = mock_check.call_args
    assert call_kwargs[1].get("char_id") or call_kwargs[0][1] == "clara"


@patch("felix.api.routes.characters.check_character_consistency")
async def test_check_consistency_returns_issues(
    mock_check: AsyncMock, seeded_driver: AsyncDriver, client: AsyncClient
) -> None:
    await _insert_character(seeded_driver, "clara", age="30 ans")
    mock_check.return_value = ConsistencyReport(
        issues=[
            ConsistencyIssue(
                type="profile_contradiction",
                severity="error",
                scene_id="scene-1",
                entity_id="clara",
                description="Age contradicts scene evidence",
                suggestion="Keep age as 30 ans",
            )
        ]
    )

    resp = await client.post(
        "/api/characters/clara/check-consistency", json={"age": "15 ans"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["issues"]) == 1
    assert data["issues"][0]["type"] == "profile_contradiction"
    assert data["issues"][0]["severity"] == "error"
