"""Trace des appels d'outil + Cypher exécutée (#78) — TDD red→green.

Quatre familles de tests :
- `QueryTrace` (calcul pur, sans driver ni LLM) : troncature des valeurs de
  paramètre longues, cap du nombre de requêtes gardées avec compteur omis.
- câblage `GenericDeps` → `RecordingDriver` : un VRAI appel d'outil contre
  Neo4j (Agent + `FunctionModel`, stub IN-PROCESS, aucun appel réseau LLM)
  fait apparaître la Cypher + ses params dans `deps.query_trace`.
- câblage `stream_pass` → `deps.query_trace` : le nom + les args de l'appel
  d'outil, ET son libellé humain, sont capturés au bon endroit.
- persistance bout en bout : un tour complet de `/api/atelier/chat` (agents
  stubs, zéro LLM réel) attache la trace au payload du DERNIER message felix
  du tour — elle doit survivre à un rechargement (GET /api/atelier/conversation).

Univers de test : Zorvun/Kelphi/Astaroth (fictifs, cf. tests/unit/test_cost.py
— aucun recoupement avec des exemples de prompt, cf. CLAUDE.md anti-leakage).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import httpx
from fastapi import FastAPI
from protest import ProTestSuite, Use, fixture
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo

from felix.api import deps as api_deps
from felix.api.routes import atelier as atelier_routes
from felix.atelier.agent import RouteDecision
from felix.atelier.pipeline import stream_pass
from felix.core import create_entity
from felix.core.deps import GenericDeps
from felix.core.tools import add_entity, find_entity
from felix.graph.driver import get_driver, setup_constraints
from felix.trace import QueryTrace

tool_trace_suite = ProTestSuite("ToolTrace")


# ─────────────────────── QueryTrace : calcul pur ────────────────────────

@tool_trace_suite.test()
def test_add_query_truncates_long_string_param_values() -> None:
    trace = QueryTrace()
    trace.add_query("MATCH (e) RETURN e", {"texte": "x" * 500, "n": 3})
    summary = trace.summary()
    assert len(summary.queries[0].params["texte"]) == 201  # 200 chars + « … »
    assert summary.queries[0].params["texte"].endswith("…")
    assert summary.queries[0].params["n"] == 3  # valeur non-string : intacte


@tool_trace_suite.test()
def test_short_param_values_are_not_touched() -> None:
    trace = QueryTrace()
    trace.add_query("MATCH (e) RETURN e", {"id": "zorvun"})
    assert trace.summary().queries[0].params == {"id": "zorvun"}


@tool_trace_suite.test()
def test_queries_beyond_cap_are_counted_not_kept() -> None:
    trace = QueryTrace()
    for i in range(250):
        trace.add_query(f"MATCH (e {{n: {i}}}) RETURN e", {})
    summary = trace.summary()
    assert len(summary.queries) == 200
    assert summary.queries_omitted == 50


@tool_trace_suite.test()
def test_merge_combines_tool_calls_and_queries() -> None:
    a = QueryTrace()
    a.add_tool_call("find_entity", {"name": "Zorvun"}, "Recherche d'informations sur Zorvun")
    a.add_query("MATCH (e) RETURN e", {"id": "zorvun"})
    b = QueryTrace()
    b.add_tool_call("list_entities", {}, "Liste des fiches")
    b.add_query("MATCH (e) RETURN e", {"id": "kelphi"})
    a.merge(b)
    summary = a.summary()
    assert [c.name for c in summary.tool_calls] == ["find_entity", "list_entities"]
    assert len(summary.queries) == 2


@tool_trace_suite.test()
def test_merge_preserves_omitted_count_across_operations() -> None:
    """Le cap de requêtes GARDÉES s'applique au total fusionné, mais le
    compteur `queries_omitted` reste la vraie somme — sinon un document à
    plusieurs blocs sous-compterait ce qu'il a réellement exécuté."""
    a = QueryTrace()
    for i in range(150):
        a.add_query(f"MATCH (e {{n: {i}}}) RETURN e", {})
    b = QueryTrace()
    for i in range(100):
        b.add_query(f"MATCH (e {{n: {i}}}) RETURN e", {})
    a.merge(b)
    summary = a.summary()
    assert len(summary.queries) == 200
    assert summary.queries_omitted == 50


@tool_trace_suite.test()
def test_empty_trace_has_no_queries_omitted() -> None:
    assert QueryTrace().summary().queries_omitted == 0


# ─────────────────────── fixture driver réel (Neo4j) ────────────────────

@fixture(max_concurrency=1)
async def _trace_driver() -> AsyncGenerator[AsyncDriver]:
    driver = get_driver()
    await setup_constraints(driver)
    try:
        yield driver
    finally:
        await driver.close()


async def _wipe(driver: AsyncDriver, proj: str) -> None:
    async with driver.session() as session:
        await session.run("MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=proj)
        await session.run("MATCH (n:Message {project: $p}) DETACH DELETE n", p=proj)
        await session.run("MATCH (n:Thread {project: $p}) DETACH DELETE n", p=proj)
        await session.run("MATCH (n:CostEntry {project: $p}) DETACH DELETE n", p=proj)
        await session.run("MATCH (n:Project {id: $p}) DETACH DELETE n", p=proj)


# ─────────── RecordingDriver : un VRAI appel d'outil contre Neo4j ───────────

def _make_single_tool_caller(
    tool_name: str, args: dict[str, object], final_text: str = "fait.",
):
    """Function pour `FunctionModel` : appelle `tool_name(**args)` au premier
    tour, renvoie du texte au second (dès que le dernier message porte le
    retour d'outil) — un stub IN-PROCESS, aucun appel réseau, cf.
    tests/unit/test_cost.py pour le même principe avec `TestModel`."""
    def model_fn(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        last = messages[-1]
        already_called = any(isinstance(p, ToolReturnPart) for p in last.parts)
        if already_called:
            return ModelResponse(parts=[TextPart(content=final_text)])
        return ModelResponse(parts=[ToolCallPart(tool_name=tool_name, args=args)])
    return model_fn


@tool_trace_suite.test()
async def test_recording_driver_captures_query_and_params_for_a_real_tool_call(
    driver: Annotated[AsyncDriver, Use(_trace_driver)],
) -> None:
    proj = "test-tool-trace-recorder-v1"
    await _wipe(driver, proj)
    try:
        await create_entity(driver, "zorvun", "Zorvun", "personnage", {}, project=proj)
        deps = GenericDeps(driver=driver, project_id=proj)
        agent = Agent(
            FunctionModel(_make_single_tool_caller("find_entity", {"name": "Zorvun"})),
            deps_type=GenericDeps, output_type=str,
        )
        agent.tool(find_entity)

        await agent.run("cherche Zorvun", deps=deps)

        queries = deps.query_trace.summary().queries
        assert queries, "aucune requête capturée — le driver de deps n'est pas proxifié ?"
        matched = [q for q in queries if q.params.get("project") == proj]
        assert matched, [q.query for q in queries]
        # find_node résout par slug ET par nom (cf. felix.core.graph.find_node) —
        # les DEUX params doivent survivre à la capture, pas seulement le texte.
        assert any(q.params.get("slug") == "zorvun" for q in matched)
    finally:
        await _wipe(driver, proj)


@tool_trace_suite.test()
async def test_stream_pass_captures_tool_name_args_and_human_label(
    driver: Annotated[AsyncDriver, Use(_trace_driver)],
) -> None:
    proj = "test-tool-trace-streampass-v1"
    await _wipe(driver, proj)
    try:
        await create_entity(driver, "kelphi", "Kelphi", "personnage", {}, project=proj)
        deps = GenericDeps(driver=driver, project_id=proj)
        agent = Agent(
            FunctionModel(_make_single_tool_caller("find_entity", {"name": "Kelphi"})),
            deps_type=GenericDeps, output_type=str,
        )
        agent.tool(find_entity)

        holder: dict = {}
        events = [
            ev async for ev in stream_pass(
                agent, "cherche Kelphi", None, deps, stream_text=False, holder=holder,
            )
        ]
        assert events == [] or all(ev.event == "tool" for ev in events)  # find_entity ne pousse pas de carte

        calls = deps.query_trace.summary().tool_calls
        assert len(calls) == 1
        assert calls[0].name == "find_entity"
        assert calls[0].args == {"name": "Kelphi"}
        assert calls[0].label == "Recherche d'informations sur Kelphi"
    finally:
        await _wipe(driver, proj)


# ─────── persistance bout en bout : /api/atelier/chat → GET /conversation ───────

def _text_only_model(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content="Bien reçu.")])


async def _text_only_stream(
    _messages: list[ModelMessage], _info: AgentInfo,
) -> AsyncGenerator[str]:
    # Le maître est streamé (stream_text=True dans stream_pass) : FunctionModel
    # exige une fonction de STREAM dédiée pour ce chemin, la fonction non-stream
    # ci-dessus ne suffit pas (cf. l'échec observé sans elle).
    yield "Bien reçu."


@tool_trace_suite.test()
async def test_chat_turn_persists_trace_in_the_last_felix_message_payload(
    driver: Annotated[AsyncDriver, Use(_trace_driver)],
) -> None:
    """Un tour complet (maître muet + extracteur qui écrit une fiche via
    add_entity) doit porter la trace (#78) DANS le payload persisté du
    DERNIER message felix du tour — même convention que le coût (cf.
    felix.api.routes.atelier) — pour qu'elle survive à un rechargement."""
    proj = "test-tool-trace-chat-v1"
    await _wipe(driver, proj)
    try:
        gate_agent = Agent(
            TestModel(custom_output_args={"fait": "Astaroth est un personnage", "noter": True}),
            output_type=RouteDecision,
        )
        master_agent: Agent[GenericDeps, str] = Agent(
            FunctionModel(_text_only_model, stream_function=_text_only_stream),
            deps_type=GenericDeps, output_type=str,
        )
        entities_agent: Agent[GenericDeps, str] = Agent(
            FunctionModel(_make_single_tool_caller(
                "add_entity", {"name": "Astaroth", "entity_type": "personnage"},
            )),
            deps_type=GenericDeps, output_type=str,
        )
        entities_agent.tool(add_entity)
        noop_agent: Agent[GenericDeps, str] = Agent(
            FunctionModel(_text_only_model), deps_type=GenericDeps, output_type=str,
        )

        test_app = FastAPI()
        test_app.include_router(atelier_routes.router)
        test_app.dependency_overrides[api_deps.get_driver] = lambda: driver
        test_app.dependency_overrides[api_deps.get_gate_agents] = lambda: {"scenario": gate_agent}
        test_app.dependency_overrides[api_deps.get_master_agents] = lambda: {"scenario": master_agent}
        test_app.dependency_overrides[api_deps.get_atelier_agents] = lambda: {"scenario": entities_agent}
        test_app.dependency_overrides[api_deps.get_relation_agents] = lambda: {"scenario": noop_agent}
        test_app.dependency_overrides[api_deps.get_chronicle_agents] = lambda: {"scenario": noop_agent}

        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/atelier/chat",
                json={"message": "Astaroth est un personnage.", "profile": "scenario", "project": proj},
            )
            assert response.status_code == 200
            assert "event: error" not in response.text, response.text
            assert "event: trace" in response.text, response.text

            conv = await client.get("/api/atelier/conversation", params={"project": proj})
        assert conv.status_code == 200
        messages = conv.json()
        tool_msgs = [m for m in messages if m["kind"] == "tool"]
        assert len(tool_msgs) == 1, messages
        payload = tool_msgs[0]["payload"]
        assert payload is not None
        assert "trace" in payload, payload
        trace = payload["trace"]
        assert [c["name"] for c in trace["tool_calls"]] == ["add_entity"]
        assert trace["tool_calls"][0]["label"] == "Création de la fiche Astaroth"
        assert trace["queries"], "la Cypher de add_entity doit apparaître dans la trace persistée"
        assert any(q["params"].get("project") == proj for q in trace["queries"])
        # Le coût (#coût) est persisté dans le MÊME payload, même convention.
        assert "cost" in payload
    finally:
        await _wipe(driver, proj)
