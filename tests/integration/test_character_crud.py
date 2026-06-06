from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Annotated
from unittest.mock import patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from protest import ProTestSuite, Use, fixture

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from tests.fixtures import seeded_driver
from tests.integration.helpers import get_char, insert_character

from felix.api.deps import get_driver
from felix.api.routes.characters import router
from felix.graph.repositories.characters import (
    delete_character_relation,
    overwrite_character_profile_fields,
    upsert_character_relation,
)
from felix.ingest.models import ConsistencyIssue, ConsistencyReport

character_crud_suite = ProTestSuite("CharacterCRUD")


async def _insert_relation(
    driver: AsyncDriver,
    a: str,
    b: str,
    relation_type: str,
    description: str | None = None,
) -> None:
    await upsert_character_relation(driver, a, b, relation_type, description=description)


# ---------------------------------------------------------------------------
# Fixture: API client
# ---------------------------------------------------------------------------


@fixture()
async def api_client(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_driver] = lambda: driver
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Repository tests: overwrite_character_profile_fields
# ---------------------------------------------------------------------------


@character_crud_suite.test()
async def test_overwrite_replaces_background(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await insert_character(driver, "clara", background="Signal recu en avril")
    await overwrite_character_profile_fields(driver, "clara", {"background": "Nouvelle bio"})
    row = await get_char(driver, "clara")
    assert row["background"] == "Nouvelle bio"


@character_crud_suite.test()
async def test_overwrite_replaces_arc(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await insert_character(driver, "clara", arc="Decouvre le signal")
    await overwrite_character_profile_fields(driver, "clara", {"arc": "Nouvel arc"})
    row = await get_char(driver, "clara")
    assert row["arc"] == "Nouvel arc"


@character_crud_suite.test()
async def test_overwrite_clears_field_with_null(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await insert_character(driver, "clara", age="30 ans", physical="Grande")
    await overwrite_character_profile_fields(driver, "clara", {"age": None})
    row = await get_char(driver, "clara")
    assert row.get("age") is None
    assert row["physical"] == "Grande"


@character_crud_suite.test()
async def test_overwrite_partial_update(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await insert_character(driver, "clara", age="30 ans", traits="Curieuse")
    await overwrite_character_profile_fields(driver, "clara", {"age": "31 ans"})
    row = await get_char(driver, "clara")
    assert row["age"] == "31 ans"
    assert row["traits"] == "Curieuse"


@character_crud_suite.test()
async def test_overwrite_returns_false_for_unknown_char(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    result = await overwrite_character_profile_fields(driver, "inconnu", {"age": "20"})
    assert result is False


@character_crud_suite.test()
async def test_overwrite_empty_dict_is_noop(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await insert_character(driver, "clara", age="30 ans")
    result = await overwrite_character_profile_fields(driver, "clara", {})
    assert result is True
    row = await get_char(driver, "clara")
    assert row["age"] == "30 ans"


# ---------------------------------------------------------------------------
# Repository tests: delete_character_relation
# ---------------------------------------------------------------------------


@character_crud_suite.test()
async def test_delete_relation_removes_edge(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await insert_character(driver, "alice")
    await insert_character(driver, "bob")
    await _insert_relation(driver, "alice", "bob", "allie")
    result = await delete_character_relation(driver, "alice", "bob", "allie")
    assert result is True


@character_crud_suite.test()
async def test_delete_relation_returns_false_if_not_found(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await insert_character(driver, "alice")
    await insert_character(driver, "bob")
    result = await delete_character_relation(driver, "alice", "bob", "ennemi")
    assert result is False


@character_crud_suite.test()
async def test_delete_relation_keeps_other_relations(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
) -> None:
    await insert_character(driver, "alice")
    await insert_character(driver, "bob")
    await _insert_relation(driver, "alice", "bob", "allie")
    await _insert_relation(driver, "alice", "bob", "collegue")
    await delete_character_relation(driver, "alice", "bob", "allie")
    # collegue should still exist
    from felix.graph.repositories.characters import get_relation_types_for_pair

    types = await get_relation_types_for_pair(driver, "alice", "bob")
    assert "collegue" in types
    assert "allie" not in types


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


# --- POST /api/characters ---


@character_crud_suite.test()
async def test_post_character_201(
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    resp = await client.post("/api/characters", json={"name": "Clara Voss", "era": "2030s"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Clara Voss"
    assert data["era"] == "2030s"
    assert data["id"] == "clara-voss"


@character_crud_suite.test()
async def test_post_character_409_duplicate(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    await insert_character(driver, "clara-voss", name="Clara Voss")
    resp = await client.post("/api/characters", json={"name": "Clara Voss", "era": "2030s"})
    assert resp.status_code == 409


@character_crud_suite.test()
async def test_post_character_422_missing_fields(
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    resp = await client.post("/api/characters", json={"name": "Clara"})
    assert resp.status_code == 422


# --- PATCH /api/characters/{char_id} ---


@character_crud_suite.test()
async def test_patch_character_200(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    await insert_character(driver, "clara", age="30 ans")
    resp = await client.patch("/api/characters/clara", json={"age": "31 ans"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["age"] == "31 ans"
    assert data["id"] == "clara"


@character_crud_suite.test()
async def test_patch_character_partial(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    await insert_character(driver, "clara", age="30 ans", traits="Curieuse")
    resp = await client.patch("/api/characters/clara", json={"age": "31 ans"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["age"] == "31 ans"
    assert data["traits"] == "Curieuse"


@character_crud_suite.test()
async def test_patch_character_clear_field(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    await insert_character(driver, "clara", age="30 ans")
    resp = await client.patch("/api/characters/clara", json={"age": None})
    assert resp.status_code == 200
    assert resp.json()["age"] is None


@character_crud_suite.test()
async def test_patch_character_404(
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    resp = await client.patch("/api/characters/inconnu", json={"age": "20"})
    assert resp.status_code == 404


@character_crud_suite.test()
async def test_patch_character_empty_body(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    await insert_character(driver, "clara", age="30 ans")
    resp = await client.patch("/api/characters/clara", json={})
    assert resp.status_code == 200
    assert resp.json()["age"] == "30 ans"


# --- PUT /api/characters/{a}/relations/{b} ---


@character_crud_suite.test()
async def test_put_relation_creates(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    await insert_character(driver, "alice")
    await insert_character(driver, "bob")
    resp = await client.put(
        "/api/characters/alice/relations/bob",
        json={"relation_type": "frere", "description": "Jumeaux"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["relation_type"] == "frere"
    assert data["other_name"] == "bob"


@character_crud_suite.test()
async def test_put_relation_updates(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    await insert_character(driver, "alice")
    await insert_character(driver, "bob")
    await _insert_relation(driver, "alice", "bob", "allie", description="Ancienne")
    resp = await client.put(
        "/api/characters/alice/relations/bob",
        json={"relation_type": "allie", "description": "Renforcee"},
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Renforcee"


@character_crud_suite.test()
async def test_put_relation_404_unknown_char(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    await insert_character(driver, "alice")
    resp = await client.put(
        "/api/characters/alice/relations/inconnu",
        json={"relation_type": "frere"},
    )
    assert resp.status_code == 404


# --- DELETE /api/characters/{a}/relations/{b} ---


@character_crud_suite.test()
async def test_delete_relation_204(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    await insert_character(driver, "alice")
    await insert_character(driver, "bob")
    await _insert_relation(driver, "alice", "bob", "allie")
    resp = await client.delete(
        "/api/characters/alice/relations/bob?relation_type=allie"
    )
    assert resp.status_code == 204


@character_crud_suite.test()
async def test_delete_relation_404(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    await insert_character(driver, "alice")
    await insert_character(driver, "bob")
    resp = await client.delete(
        "/api/characters/alice/relations/bob?relation_type=ennemi"
    )
    assert resp.status_code == 404


@character_crud_suite.test()
async def test_delete_relation_requires_type(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    await insert_character(driver, "alice")
    await insert_character(driver, "bob")
    resp = await client.delete("/api/characters/alice/relations/bob")
    assert resp.status_code == 422


# --- POST /api/characters/{char_id}/check-consistency ---


@character_crud_suite.test()
async def test_check_consistency_404(
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    resp = await client.post(
        "/api/characters/inconnu/check-consistency", json={"age": "20"}
    )
    assert resp.status_code == 404


@character_crud_suite.test()
async def test_check_consistency_empty_body(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    await insert_character(driver, "clara", age="30 ans")
    resp = await client.post("/api/characters/clara/check-consistency", json={})
    assert resp.status_code == 200
    assert resp.json()["issues"] == []


@character_crud_suite.test()
async def test_check_consistency_calls_agent(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    await insert_character(driver, "clara", age="30 ans")
    with patch("felix.api.routes.characters.check_character_consistency") as mock_check:
        mock_check.return_value = ConsistencyReport(issues=[])
        resp = await client.post(
            "/api/characters/clara/check-consistency", json={"age": "25 ans"}
        )
        assert resp.status_code == 200
        mock_check.assert_called_once()
        call_kwargs = mock_check.call_args
        assert call_kwargs[1].get("char_id") or call_kwargs[0][1] == "clara"


@character_crud_suite.test()
async def test_check_consistency_returns_issues(
    driver: Annotated[AsyncDriver, Use(seeded_driver)],
    client: Annotated[AsyncClient, Use(api_client)],
) -> None:
    await insert_character(driver, "clara", age="30 ans")
    with patch("felix.api.routes.characters.check_character_consistency") as mock_check:
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
