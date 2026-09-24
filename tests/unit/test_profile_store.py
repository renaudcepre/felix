"""Persistance du profil évolué par projet (Étape 3) — round-trip (dé)sérialisation
pur + charge/sauvegarde Neo4j sur le méta-nœud ``:ProjectProfile``.

Univers de TEST : presse à balles BX-9 (cf. [[feedback_prompt_test_leakage]]).
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated

from protest import ProTestSuite, Use, fixture

from felix.core.graph import NARRATIVE_REL
from felix.core.profile import EMERGENT_SEED_PROFILE, EntityType, Profile, RelationSpec
from felix.core.profile_store import (
    load_project_profile,
    load_project_profile_version,
    load_rejected_changes,
    profile_from_dict,
    profile_to_dict,
    save_project_profile,
    save_rejected_change,
)
from felix.core.schema_changes import MergeTypes, PromoteVerbs
from felix.graph.driver import get_driver, setup_constraints

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

profile_store_suite = ProTestSuite("ProfileStore")

PROJ = "test-profile-store"
PROJ_B = PROJ + "-b"


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n:ProjectProfile) WHERE n.project IN [$p, $p2] DETACH DELETE n",
            p=PROJ, p2=PROJ_B,
        )


@fixture(max_concurrency=1)
async def _driver() -> AsyncGenerator[AsyncDriver]:
    driver = get_driver()
    await setup_constraints(driver)
    try:
        yield driver
    finally:
        await _wipe(driver)
        await driver.close()


_RICH_PROFILE = Profile(
    name="pilote", description="un profil de test riche",
    entity_types=(
        EntityType("organe", ("fonction", "emplacement"), "note sur organe"),
        EntityType("commande", ("nature",)),
    ),
    modeling_rules=("règle 1", "règle 2"),
    consistency_rules=("cohérence 1",),
    relation_vocabulary=(
        RelationSpec(
            "CONTROLS", "pilote un réglage",
            subjects=("commande",), objects=("organe", "parametre"),
            allow_self=False, examples="règle, pilote",
        ),
        RelationSpec("PART_OF", "fait partie de", subjects=("organe",), objects=("organe",),
                     allow_self=True),
    ),
    narrative_rel=NARRATIVE_REL,
    manages_events=False,
    code_only_relations=("DESCRIBED_IN",),
)


# ──────────────────── profile_to_dict / profile_from_dict (pur) ────────────────────

@profile_store_suite.test()
def test_round_trip_exact_on_rich_profile() -> None:
    assert profile_from_dict(profile_to_dict(_RICH_PROFILE)) == _RICH_PROFILE


@profile_store_suite.test()
def test_round_trip_exact_on_seed_profile() -> None:
    assert profile_from_dict(profile_to_dict(EMERGENT_SEED_PROFILE)) == EMERGENT_SEED_PROFILE


@profile_store_suite.test()
def test_round_trip_preserves_tuples() -> None:
    data = profile_to_dict(_RICH_PROFILE)
    restored = profile_from_dict(data)
    assert isinstance(restored.entity_types, tuple)
    assert isinstance(restored.modeling_rules, tuple)
    assert isinstance(restored.relation_vocabulary, tuple)
    assert isinstance(restored.relation_vocabulary[0].subjects, tuple)
    assert isinstance(restored.code_only_relations, tuple)


@profile_store_suite.test()
def test_round_trip_survives_json_serialization() -> None:
    """Le VRAI chemin de persistance passe par une string JSON (cf. save_project_profile)."""
    dumped = json.dumps(profile_to_dict(_RICH_PROFILE))
    restored = profile_from_dict(json.loads(dumped))
    assert restored == _RICH_PROFILE


# ──────────────────── load/save (Neo4j) ────────────────────

@profile_store_suite.test()
async def test_load_returns_none_when_nothing_stored(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    assert await load_project_profile(driver, project=PROJ) is None


@profile_store_suite.test()
async def test_save_then_load_round_trips(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    await save_project_profile(driver, _RICH_PROFILE, project=PROJ)
    loaded = await load_project_profile(driver, project=PROJ)
    assert loaded == _RICH_PROFILE


@profile_store_suite.test()
async def test_save_increments_version_from_one(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    v1 = await save_project_profile(driver, EMERGENT_SEED_PROFILE, project=PROJ)
    v2 = await save_project_profile(driver, _RICH_PROFILE, project=PROJ)
    assert v1 == 1
    assert v2 == 2


@profile_store_suite.test()
async def test_save_scoped_per_project(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    await save_project_profile(driver, _RICH_PROFILE, project=PROJ)
    assert await load_project_profile(driver, project=PROJ_B) is None


# ──────────────────── refus persistés (file de validation, Étape 8) ────────────────────
# Un `rejected` SIBLING de `data` sur le même :ProjectProfile — pas dans le
# Profile lui-même (round-trip profile_to_dict intact, cf. tests ci-dessus).

@profile_store_suite.test()
async def test_load_rejected_changes_empty_when_nothing_stored(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    assert await load_rejected_changes(driver, project=PROJ) == []


@profile_store_suite.test()
async def test_save_then_load_rejected_change_round_trips(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    change = PromoteVerbs(verbe_slugs=["regle"], rel_type="CONTROLS")
    await save_rejected_change(driver, change, project=PROJ)
    assert await load_rejected_changes(driver, project=PROJ) == [change.model_dump()]


@profile_store_suite.test()
async def test_save_rejected_change_accumulates(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    await save_rejected_change(
        driver, PromoteVerbs(verbe_slugs=["regle"], rel_type="CONTROLS"), project=PROJ,
    )
    await save_rejected_change(
        driver, MergeTypes(sources=["verins"], target="verin"), project=PROJ,
    )
    rejected = await load_rejected_changes(driver, project=PROJ)
    assert len(rejected) == 2
    assert {r["kind"] for r in rejected} == {"promote_verbs", "merge_types"}


@profile_store_suite.test()
async def test_save_rejected_change_scoped_per_project(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    await save_rejected_change(
        driver, PromoteVerbs(verbe_slugs=["regle"], rel_type="CONTROLS"), project=PROJ,
    )
    assert await load_rejected_changes(driver, project=PROJ_B) == []


@profile_store_suite.test()
async def test_save_rejected_change_does_not_create_stored_profile(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Refuser une proposition avant toute validation ne doit PAS faire apparaître
    un profil stocké (`data` reste absent) — seul `rejected` est posé."""
    await _wipe(driver)
    await save_rejected_change(
        driver, PromoteVerbs(verbe_slugs=["regle"], rel_type="CONTROLS"), project=PROJ,
    )
    assert await load_project_profile(driver, project=PROJ) is None


# ──────────────────── version (lecture seule, GET /api/schema/profile) ────────────────────

@profile_store_suite.test()
async def test_load_version_is_zero_when_nothing_stored(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    assert await load_project_profile_version(driver, project=PROJ) == 0


@profile_store_suite.test()
async def test_load_version_matches_save_project_profile(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    saved = await save_project_profile(driver, EMERGENT_SEED_PROFILE, project=PROJ)
    assert await load_project_profile_version(driver, project=PROJ) == saved
