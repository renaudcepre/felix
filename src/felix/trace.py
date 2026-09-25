"""Trace UNIQUE des appels d'outils et des requêtes Cypher d'une opération
(#78) — même design que `felix.cost.CostLedger` : un recorder par opération
(tour de chat, import de document), porté par `GenericDeps`, alimenté par TOUS
les appelants (`stream_pass` pour les appels d'outil, la session Neo4j
proxifiée pour les requêtes réellement exécutées), jamais une liste ad hoc
recréée par l'appelant (cf. CLAUDE.md « des systèmes, pas du cas par cas »).

Aucune table tool→requête écrite à la main : `RecordingDriver` capture la
Cypher AU MOMENT où elle s'exécute, quel que soit l'endroit du code qui
l'émet (tools.py, graph.py, …) — la trace est donc TOUJOURS exacte, jamais une
reconstruction qui peut driver du code réel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, LiteralString, Self

from pydantic import BaseModel

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncResult, AsyncSession, Query

# Une valeur de paramètre plus longue que ça est coupée — un extrait de texte
# source ou un résumé long dans les params ne doit pas gonfler la trace.
_MAX_PARAM_VALUE_LEN = 200
# Au-delà, les requêtes supplémentaires ne sont plus GARDÉES (mais restent
# COMPTÉES) — la trace affiche « +N requêtes » plutôt qu'une liste sans fin.
_MAX_QUERIES = 200


def _truncate_value(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _MAX_PARAM_VALUE_LEN:
        return value[:_MAX_PARAM_VALUE_LEN] + "…"
    return value


def _truncate_params(params: dict[str, Any]) -> dict[str, Any]:
    return {k: _truncate_value(v) for k, v in params.items()}


class ToolCallEntry(BaseModel):
    """Un appel d'outil du LLM — nom + args bruts + libellé humain (calculé à
    la capture, cf. `felix.core.tools.label_for_tool_call`)."""

    name: str
    args: dict[str, Any]
    label: str


class QueryEntry(BaseModel):
    """Une requête Cypher réellement exécutée pendant l'opération — texte +
    paramètres (valeurs longues tronquées, cf. `_truncate_params`)."""

    query: str
    params: dict[str, Any]


class TraceSummary(BaseModel):
    """Vue exportable d'un `QueryTrace` — même esprit que `CostSummary` :
    calculée une fois, envoyée telle quelle en SSE et persistée dans le
    payload du message."""

    tool_calls: list[ToolCallEntry] = []
    queries: list[QueryEntry] = []
    # Requêtes VUES au-delà du cap `_MAX_QUERIES`, non gardées individuellement
    # mais pas perdues silencieusement — le front affiche « +N requêtes ».
    queries_omitted: int = 0


@dataclass
class QueryTrace:
    """Le recorder UNIQUE d'une opération. `add_tool_call` est appelé par
    `stream_pass` (felix.atelier.pipeline) pour chaque appel d'outil vu dans
    le run pydantic-ai ; `add_query` est appelé par `RecordingDriver` à CHAQUE
    `session().run()` — capturé À L'EXÉCUTION, jamais reconstruit depuis une
    table tool→requête à la main."""

    _tool_calls: list[ToolCallEntry] = field(default_factory=list)
    _queries: list[QueryEntry] = field(default_factory=list)
    _queries_seen: int = 0

    def add_tool_call(self, name: str, args: dict[str, Any], label: str) -> None:
        self._tool_calls.append(ToolCallEntry(name=name, args=args, label=label))

    def add_query(self, query: str, params: dict[str, Any]) -> None:
        self._queries_seen += 1
        if len(self._queries) < _MAX_QUERIES:
            self._queries.append(QueryEntry(query=query, params=_truncate_params(params)))

    def merge(self, other: QueryTrace) -> None:
        """Fusionne les entrées d'un autre trace (ex. le trace d'un bloc
        d'ingestion dans le trace du document entier) — même esprit que
        `CostLedger.merge` / `GenericDeps.touched_ids |= chunk_deps.touched_ids`.
        Le cap de requêtes GARDÉES s'applique au total fusionné (pas par bloc) ;
        `_queries_seen` reste la vraie somme, donc `queries_omitted` reste exact."""
        for call in other._tool_calls:  # même classe, accès direct légitime
            self._tool_calls.append(call)
        for entry in other._queries:
            self._queries_seen += 1
            if len(self._queries) < _MAX_QUERIES:
                self._queries.append(entry)
        # Les requêtes déjà au-delà du cap CHEZ `other` doivent rester comptées.
        self._queries_seen += other._queries_seen - len(other._queries)

    def summary(self) -> TraceSummary:
        return TraceSummary(
            tool_calls=list(self._tool_calls),
            queries=list(self._queries),
            queries_omitted=max(0, self._queries_seen - len(self._queries)),
        )


class _RecordingSession:
    """Session Neo4j PROXY — enregistre CHAQUE requête exécutée dans le trace,
    puis délègue à la vraie session. Aucune logique Cypher : un passe-plat."""

    def __init__(self, real_session: AsyncSession, trace: QueryTrace) -> None:
        self._real = real_session
        self._trace = trace

    async def __aenter__(self) -> Self:
        await self._real.__aenter__()
        return self

    async def __aexit__(self, *exc_info: object) -> Any:
        return await self._real.__aexit__(*exc_info)

    async def run(
        self,
        query: LiteralString | Query,
        parameters: dict[str, Any] | None = None,
        **kwparameters: Any,
    ) -> AsyncResult:
        params = dict(parameters or {})
        params.update(kwparameters)
        self._trace.add_query(str(query), params)
        return await self._real.run(query, parameters, **kwparameters)


class RecordingDriver:
    """Proxy fin posé sur le driver Neo4j RÉEL, un par opération (créé dans
    `GenericDeps.__post_init__`, cf. felix.core.deps) — capture CHAQUE requête
    exécutée par `session().run()` avant de la déléguer. Seule la surface
    réellement utilisée par le code (`session()`) est proxifiée : le driver
    applicatif n'appelle jamais `execute_query`/`verify_connectivity` sur une
    instance portée par `GenericDeps` (seul `close()` existe, sur le driver
    APPLICATIF, jamais sur celui-ci)."""

    def __init__(self, real_driver: AsyncDriver, trace: QueryTrace) -> None:
        self._real = real_driver
        self._trace = trace

    def session(self, *args: Any, **kwargs: Any) -> _RecordingSession:
        return _RecordingSession(self._real.session(*args, **kwargs), self._trace)
