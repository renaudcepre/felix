"""Réordonnancement des événements (#44) — insertion avec `avant` et `move_event`.

Deux pans :
- Tests PURS (sans Neo4j) : fonctions d'aide resolve_event_fragment /
  compute_insert_before / compute_move_before / compute_move_after.
- Tests avec driver réel : insertion à la création (add_event + avant),
  déplacement a posteriori (move_event), refus, étanchéité projet.

Anti-leakage : les noms de ce module (Prol, Sevne, Tarvex) ne doivent PAS
apparaître dans les prompts des agents (src/felix/) — vérification ci-dessous.
"""
from __future__ import annotations

import pathlib
import re
from typing import TYPE_CHECKING, Annotated
from unittest.mock import MagicMock

from protest import ProTestSuite, Use, fixture

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

from pydantic_ai import RunContext

from felix.core.deps import GenericDeps
from felix.core.tools import (
    add_event,
    compute_insert_before,
    compute_move_after,
    compute_move_before,
    move_event,
    resolve_event_fragment,
)
from felix.graph.driver import get_driver, setup_constraints

event_reorder_suite = ProTestSuite("EventReorder")

# ─────────────────── Noms dédiés à ces tests (univers isolé) ────────────────
_TEST_NAMES = ("Prol", "Sevne", "Tarvex")

# ─────────────────────── Fixture driver ─────────────────────────────────────


@fixture(max_concurrency=1)
async def _reorder_driver() -> AsyncGenerator[AsyncDriver]:
    """Ouvre un driver Neo4j pour la suite ; le ferme en teardown."""
    driver = get_driver()
    await setup_constraints(driver)
    try:
        yield driver
    finally:
        await driver.close()


# ──────────────── Tests PURS : resolve_event_fragment ────────────────────────

_EVENTS = [
    {"id": "event-1", "ordre": 1, "resume": "Prol franchit la porte blindée"},
    {"id": "event-2", "ordre": 2, "resume": "Sevne active le détonateur"},
    {"id": "event-3", "ordre": 3, "resume": "Tarvex s'effondre dans la fumée"},
]


@event_reorder_suite.test()
def test_resolve_unique_match() -> None:
    """Fragment à match unique → retourne l'événement, aucune erreur."""
    event, err = resolve_event_fragment(_EVENTS, "détonateur")
    assert err is None
    assert event is not None
    assert event["id"] == "event-2"


@event_reorder_suite.test()
def test_resolve_not_found() -> None:
    """Fragment sans match → None + message d'erreur (refus terminal)."""
    event, err = resolve_event_fragment(_EVENTS, "inexistant-xyz")
    assert event is None
    assert err is not None
    assert "introuvable" in err.lower() or "aucun" in err.lower()


@event_reorder_suite.test()
def test_resolve_not_found_lists_resumes() -> None:
    """Le refus « introuvable » LISTE les résumés existants : le modèle dit
    naturellement « la mort de X » quand le résumé dit « X meurt » — sans la
    liste sous les yeux, il s'entête en variations et boucle jusqu'au
    request_limit (vécu : UsageLimitExceeded à 50 sur flashback_correction).
    Donner les résumés exacts n'est pas un contournement (#59 vise les
    interdictions sémantiques) : c'est l'information pour réussir au 2e essai."""
    _event, err = resolve_event_fragment(_EVENTS, "la mort de Prol")
    assert err is not None
    for resume in ("Prol franchit la porte blindée",
                   "Sevne active le détonateur",
                   "Tarvex s'effondre dans la fumée"):
        assert resume in err, f"le refus doit lister « {resume} »"


@event_reorder_suite.test()
def test_resolve_ambiguous() -> None:
    """Fragment correspondant à plusieurs events → None + message d'erreur."""
    ambig_events = [
        {"id": "event-1", "ordre": 1, "resume": "Prol franchit la porte"},
        {"id": "event-2", "ordre": 2, "resume": "Sevne ouvre la valve"},
        {"id": "event-3", "ordre": 3, "resume": "Tarvex s'effondre"},
    ]
    event, err = resolve_event_fragment(ambig_events, "la ")
    assert event is None
    assert err is not None
    assert "ambigu" in err.lower() or "plusieurs" in err.lower()


@event_reorder_suite.test()
def test_resolve_ambiguous_lists_matches() -> None:
    """Le refus « ambigu » liste les candidats en conflit (mêmes raisons que
    le refus introuvable : un fragment plus précis se choisit en les voyant)."""
    ambig_events = [
        {"id": "event-1", "ordre": 1, "resume": "Prol franchit la porte"},
        {"id": "event-2", "ordre": 2, "resume": "Sevne ouvre la valve"},
    ]
    _event, err = resolve_event_fragment(ambig_events, "e")
    assert err is not None
    assert "Prol franchit la porte" in err
    assert "Sevne ouvre la valve" in err


@event_reorder_suite.test()
def test_resolve_case_insensitive() -> None:
    """Match insensible à la casse."""
    event, err = resolve_event_fragment(_EVENTS, "DÉTONATEUR")
    assert err is None
    assert event is not None
    assert event["id"] == "event-2"


@event_reorder_suite.test()
def test_resolve_accent_insensitive() -> None:
    """Match insensible aux accents."""
    event, err = resolve_event_fragment(_EVENTS, "detona")
    assert err is None
    assert event is not None
    assert event["id"] == "event-2"


# ──────────────── Tests PURS : compute_insert_before ────────────────────────


@event_reorder_suite.test()
def test_insert_before_first() -> None:
    """Insérer avant le premier élément."""
    result = compute_insert_before(["a", "b", "c"], "x", "a")
    assert result == ["x", "a", "b", "c"]


@event_reorder_suite.test()
def test_insert_before_middle() -> None:
    """Insérer avant un élément du milieu."""
    result = compute_insert_before(["a", "b", "c"], "x", "b")
    assert result == ["a", "x", "b", "c"]


@event_reorder_suite.test()
def test_insert_before_last() -> None:
    """Insérer avant le dernier élément."""
    result = compute_insert_before(["a", "b", "c"], "x", "c")
    assert result == ["a", "b", "x", "c"]


# ──────────────── Tests PURS : compute_move_before / compute_move_after ──────


@event_reorder_suite.test()
def test_move_before() -> None:
    """Déplacer un élément avant un autre."""
    result = compute_move_before(["a", "b", "c", "d"], "c", "b")
    assert result == ["a", "c", "b", "d"]


@event_reorder_suite.test()
def test_move_after() -> None:
    """Déplacer un élément après un autre."""
    result = compute_move_after(["a", "b", "c", "d"], "b", "c")
    assert result == ["a", "c", "b", "d"]


@event_reorder_suite.test()
def test_move_before_to_first() -> None:
    """Déplacer un élément avant le premier."""
    result = compute_move_before(["a", "b", "c"], "c", "a")
    assert result == ["c", "a", "b"]


@event_reorder_suite.test()
def test_move_after_to_last() -> None:
    """Déplacer un élément après le dernier."""
    result = compute_move_after(["a", "b", "c"], "a", "c")
    assert result == ["b", "c", "a"]


# ──────────── Helpers Neo4j ─────────────────────────────────────────────────


async def _seed_events(driver: AsyncDriver, proj: str, resumes: list[str]) -> list[str]:
    """Seed rapide d'événements en séquence pour les tests Neo4j."""
    ids = []
    async with driver.session() as session:
        for i, resume in enumerate(resumes, start=1):
            eid = f"event-{i}"
            await session.run(
                "MERGE (e:GenEntity {id: $id, project: $project})"
                " SET e.name = $resume, e.entity_type = 'evenement',"
                "     e.resume = $resume, e.ordre = $ordre",
                id=eid, project=proj, resume=resume, ordre=i,
            )
            ids.append(eid)
        for i in range(len(ids) - 1):
            await session.run(
                "MATCH (a:GenEntity {id: $a, project: $p}),"
                " (b:GenEntity {id: $b, project: $p})"
                " MERGE (a)-[:REL {rel_type: 'NEXT'}]->(b)",
                a=ids[i], b=ids[i + 1], p=proj,
            )
    return ids


async def _get_events(driver: AsyncDriver, proj: str) -> list[dict]:
    """Lit tous les événements du projet, triés par ordre."""
    async with driver.session() as session:
        result = await session.run(
            "MATCH (e:GenEntity {entity_type: 'evenement', project: $project})"
            " RETURN e.id AS id, e.ordre AS ordre, e.resume AS resume"
            " ORDER BY e.ordre",
            project=proj,
        )
        return [dict(r) for r in await result.data()]


async def _get_next_chain(driver: AsyncDriver, proj: str) -> list[tuple[str, str]]:
    """Retourne les arêtes NEXT (from_id, to_id) du projet."""
    async with driver.session() as session:
        result = await session.run(
            "MATCH (a:GenEntity {entity_type: 'evenement', project: $project})"
            "-[:REL {rel_type: 'NEXT'}]->"
            "(b:GenEntity {entity_type: 'evenement', project: $project})"
            " RETURN a.id AS from_id, b.id AS to_id ORDER BY a.ordre",
            project=proj,
        )
        return [(r["from_id"], r["to_id"]) for r in await result.data()]


async def _wipe_proj(driver: AsyncDriver, proj: str) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n:GenEntity {project: $project}) DETACH DELETE n", project=proj
        )


def _make_ctx(driver: AsyncDriver, proj: str) -> RunContext[GenericDeps]:
    deps = GenericDeps(driver=driver, project_id=proj)
    ctx = MagicMock(spec=RunContext)
    ctx.deps = deps
    return ctx  # type: ignore[return-value]


# ──────────── Tests avec driver : add_event avant (insertion à la création) ──


@event_reorder_suite.test()
async def test_add_event_avant_ordres_contigus(
    driver: Annotated[AsyncDriver, Use(_reorder_driver)],
) -> None:
    """add_event avec avant= → ordres 1..N contigus, chaîne NEXT recousue."""
    proj = "test-reorder-insert-v1"
    await _wipe_proj(driver, proj)
    try:
        await _seed_events(driver, proj, [
            "Prol franchit la porte blindée",
            "Sevne active le détonateur",
        ])
        ctx = _make_ctx(driver, proj)

        result = await add_event(
            ctx,
            resume="Tarvex s'effondre dans la fumée",
            avant="Sevne active",
        )
        assert "Tarvex" in result, f"Attendu 'Tarvex' dans la réponse : {result}"

        events = await _get_events(driver, proj)
        assert len(events) == 3, f"Attendu 3 events, obtenu {len(events)}"

        ordres = [e["ordre"] for e in events]
        assert sorted(ordres) == list(range(1, 4)), f"Ordres non contigus : {ordres}"

        idx_tarvex = next(
            i for i, e in enumerate(events) if "Tarvex" in str(e.get("resume", ""))
        )
        idx_sevne = next(
            i for i, e in enumerate(events) if "Sevne" in str(e.get("resume", ""))
        )
        assert idx_tarvex < idx_sevne, (
            f"Tarvex (pos {idx_tarvex}) doit être avant Sevne (pos {idx_sevne})"
        )

        chain = await _get_next_chain(driver, proj)
        assert len(chain) == 2, f"Attendu 2 arêtes NEXT, obtenu {len(chain)} : {chain}"

        ids_ordered = [e["id"] for e in events]
        expected_chain = [(ids_ordered[i], ids_ordered[i + 1]) for i in range(2)]
        assert chain == expected_chain, (
            f"Chaîne NEXT incorrecte.\nAttendu : {expected_chain}\nObtenu  : {chain}"
        )
    finally:
        await _wipe_proj(driver, proj)


@event_reorder_suite.test()
async def test_add_event_avant_reference_introuvable(
    driver: Annotated[AsyncDriver, Use(_reorder_driver)],
) -> None:
    """add_event avec avant= introuvable → refus terminal + base intacte."""
    proj = "test-reorder-notfound-v1"
    await _wipe_proj(driver, proj)
    try:
        await _seed_events(driver, proj, ["Prol franchit la porte blindée"])
        ctx = _make_ctx(driver, proj)

        result = await add_event(
            ctx,
            resume="Sevne active le détonateur",
            avant="fragment-inexistant-xyz",
        )
        assert "introuvable" in result.lower() or "aucun" in result.lower(), (
            f"Attendu un message de refus, obtenu : {result}"
        )

        events = await _get_events(driver, proj)
        assert len(events) == 1, (
            f"La base devrait être intacte (1 event), obtenu {len(events)}"
        )
    finally:
        await _wipe_proj(driver, proj)


@event_reorder_suite.test()
async def test_add_event_avant_reference_ambigue(
    driver: Annotated[AsyncDriver, Use(_reorder_driver)],
) -> None:
    """add_event avec avant= ambigu (2 matches) → refus terminal + base intacte."""
    proj = "test-reorder-ambig-v1"
    await _wipe_proj(driver, proj)
    try:
        await _seed_events(driver, proj, [
            "Prol franchit la porte blindée",
            "Sevne verrouille la porte de secours",
        ])
        ctx = _make_ctx(driver, proj)

        result = await add_event(
            ctx,
            resume="Tarvex s'effondre",
            avant="la porte",
        )
        assert "ambigu" in result.lower() or "plusieurs" in result.lower(), (
            f"Attendu un message d'ambiguïté, obtenu : {result}"
        )

        events = await _get_events(driver, proj)
        assert len(events) == 2, (
            f"La base devrait être intacte (2 events), obtenu {len(events)}"
        )
    finally:
        await _wipe_proj(driver, proj)


# ──────────── Tests avec driver : move_event ────────────────────────────────


@event_reorder_suite.test()
async def test_move_event_avant_ordres_corrects(
    driver: Annotated[AsyncDriver, Use(_reorder_driver)],
) -> None:
    """move_event avant → ordres 1..N contigus, chaîne NEXT recousue correctement."""
    proj = "test-reorder-move-avant-v1"
    await _wipe_proj(driver, proj)
    try:
        await _seed_events(driver, proj, [
            "Prol franchit la porte blindée",
            "Sevne active le détonateur",
            "Tarvex s'effondre dans la fumée",
        ])
        ctx = _make_ctx(driver, proj)

        result = await move_event(
            ctx,
            resume="Tarvex s'effondre",
            position="avant",
            reference="Prol franchit",
        )
        assert "Tarvex" in result, f"Attendu 'Tarvex' dans la réponse : {result}"

        events = await _get_events(driver, proj)
        assert len(events) == 3

        ordres = [e["ordre"] for e in events]
        assert sorted(ordres) == [1, 2, 3], f"Ordres non contigus : {ordres}"

        assert "Tarvex" in str(events[0].get("resume", "")), (
            f"Tarvex devrait être en tête : {[e['resume'] for e in events]}"
        )

        chain = await _get_next_chain(driver, proj)
        assert len(chain) == 2, f"Attendu 2 arêtes NEXT, obtenu {len(chain)}"

        ids_ordered = [e["id"] for e in events]
        expected_chain = [
            (ids_ordered[0], ids_ordered[1]),
            (ids_ordered[1], ids_ordered[2]),
        ]
        assert chain == expected_chain, (
            f"Chaîne NEXT incorrecte.\nAttendu : {expected_chain}\nObtenu  : {chain}"
        )
    finally:
        await _wipe_proj(driver, proj)


@event_reorder_suite.test()
async def test_move_event_apres_ordres_corrects(
    driver: Annotated[AsyncDriver, Use(_reorder_driver)],
) -> None:
    """move_event apres → ordres 1..N contigus, chaîne NEXT recousue correctement."""
    proj = "test-reorder-move-apres-v1"
    await _wipe_proj(driver, proj)
    try:
        await _seed_events(driver, proj, [
            "Prol franchit la porte blindée",
            "Sevne active le détonateur",
            "Tarvex s'effondre dans la fumée",
        ])
        ctx = _make_ctx(driver, proj)

        result = await move_event(
            ctx,
            resume="Prol franchit",
            position="apres",
            reference="Sevne active",
        )
        assert "Prol" in result, f"Attendu 'Prol' dans la réponse : {result}"

        events = await _get_events(driver, proj)
        ordres = [e["ordre"] for e in events]
        assert sorted(ordres) == [1, 2, 3], f"Ordres non contigus : {ordres}"

        resume_order = [e["resume"] for e in events]
        assert "Sevne" in resume_order[0], f"Sevne devrait être premier : {resume_order}"
        assert "Prol" in resume_order[1], f"Prol devrait être deuxième : {resume_order}"
        assert "Tarvex" in resume_order[2], f"Tarvex devrait être troisième : {resume_order}"
    finally:
        await _wipe_proj(driver, proj)


@event_reorder_suite.test()
async def test_move_event_reference_introuvable(
    driver: Annotated[AsyncDriver, Use(_reorder_driver)],
) -> None:
    """move_event référence introuvable → refus + base intacte."""
    proj = "test-reorder-move-notfound-v1"
    await _wipe_proj(driver, proj)
    try:
        await _seed_events(driver, proj, [
            "Prol franchit la porte blindée",
            "Sevne active le détonateur",
        ])
        ordres_avant = [e["ordre"] for e in await _get_events(driver, proj)]
        ctx = _make_ctx(driver, proj)

        result = await move_event(
            ctx,
            resume="Prol franchit",
            position="avant",
            reference="fragment-inexistant-xyz",
        )
        assert "introuvable" in result.lower() or "aucun" in result.lower()

        ordres_apres = [e["ordre"] for e in await _get_events(driver, proj)]
        assert ordres_avant == ordres_apres, "La base ne devrait pas avoir changé"
    finally:
        await _wipe_proj(driver, proj)


@event_reorder_suite.test()
async def test_move_event_resume_ambigu(
    driver: Annotated[AsyncDriver, Use(_reorder_driver)],
) -> None:
    """move_event résumé ambigu → refus + base intacte."""
    proj = "test-reorder-move-ambig-v1"
    await _wipe_proj(driver, proj)
    try:
        await _seed_events(driver, proj, [
            "Prol franchit la porte blindée",
            "Sevne force la porte de secours",
        ])
        ordres_avant = [e["ordre"] for e in await _get_events(driver, proj)]
        ctx = _make_ctx(driver, proj)

        result = await move_event(
            ctx,
            resume="la porte",
            position="avant",
            reference="Sevne",
        )
        assert "ambigu" in result.lower() or "plusieurs" in result.lower()

        ordres_apres = [e["ordre"] for e in await _get_events(driver, proj)]
        assert ordres_avant == ordres_apres
    finally:
        await _wipe_proj(driver, proj)


@event_reorder_suite.test()
async def test_project_isolation(
    driver: Annotated[AsyncDriver, Use(_reorder_driver)],
) -> None:
    """Les events d'un autre projet ne sont jamais touchés ni renumérotés."""
    proj_a = "test-reorder-iso-a-v1"
    proj_b = "test-reorder-iso-b-v1"
    for p in (proj_a, proj_b):
        await _wipe_proj(driver, p)
    try:
        await _seed_events(driver, proj_b, [
            "Prol franchit la porte blindée",
            "Sevne active le détonateur",
        ])
        events_b_avant = await _get_events(driver, proj_b)

        await _seed_events(driver, proj_a, [
            "Tarvex s'effondre dans la fumée",
        ])
        ctx_a = _make_ctx(driver, proj_a)

        await add_event(
            ctx_a,
            resume="Le générateur explose",
            avant="Tarvex s'effondre",
        )

        events_b_apres = await _get_events(driver, proj_b)
        assert len(events_b_avant) == len(events_b_apres), (
            "Le projet B ne devrait pas avoir changé de nombre d'events"
        )
        for before, after in zip(events_b_avant, events_b_apres, strict=False):
            assert before["ordre"] == after["ordre"], (
                f"L'ordre du projet B a changé : "
                f"{before['id']} {before['ordre']} → {after['ordre']}"
            )
    finally:
        for p in (proj_a, proj_b):
            await _wipe_proj(driver, p)


# ─────────────────────────── Anti-leakage ────────────────────────────────────


@event_reorder_suite.test()
def test_no_test_names_in_prompts() -> None:
    """Les noms utilisés par ces tests n'entrent JAMAIS dans les prompts des agents."""
    src = pathlib.Path(__file__).parents[3] / "src" / "felix"
    leaked = []
    for py in src.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for name in _TEST_NAMES:
            if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
                leaked.append(f"{name} dans {py.relative_to(src.parent.parent)}")
    assert not leaked, f"noms de test présents dans les sources : {leaked}"
