from __future__ import annotations

from typing import Annotated, TypeAlias

import chromadb
from fastapi import Depends, Request
from neo4j import AsyncDriver
from pydantic_ai import Agent


def get_driver(request: Request) -> AsyncDriver:
    return request.app.state.driver


def get_collection(request: Request) -> chromadb.Collection:
    return request.app.state.collection


def get_gate_agent(request: Request) -> Agent:
    """Gate de routage stateless (RouteDecision) : décide si le tour doit extraire.
    Unique (pas par profil) — appelé avec le message SEUL, jamais d'historique."""
    return request.app.state.gate_agent


def get_master_agents(request: Request) -> dict[str, Agent]:
    """Agents « maître » (passe 0) pré-construits par profil : mènent la
    conversation (lecture seule, purement conversationnels)."""
    return request.app.state.master_agents


def get_atelier_agents(request: Request) -> dict[str, Agent]:
    """Agents du bot B pré-construits par profil (scenario/chantier/none)."""
    return request.app.state.atelier_agents


def get_relation_agents(request: Request) -> dict[str, Agent]:
    """Sous-agents « relieur » (2e passe) pré-construits par profil."""
    return request.app.state.relation_agents


def get_chronicle_agents(request: Request) -> dict[str, Agent]:
    """Sous-agents « chroniqueur » (3e passe, événements) pré-construits par profil."""
    return request.app.state.chronicle_agents


Neo4jDriver: TypeAlias = Annotated[AsyncDriver, Depends(get_driver)]
Collection: TypeAlias = Annotated[chromadb.Collection, Depends(get_collection)]
GateAgentDep: TypeAlias = Annotated[Agent, Depends(get_gate_agent)]
MasterAgentsDep: TypeAlias = Annotated[dict[str, Agent], Depends(get_master_agents)]
AtelierAgentsDep: TypeAlias = Annotated[dict[str, Agent], Depends(get_atelier_agents)]
RelationAgentsDep: TypeAlias = Annotated[dict[str, Agent], Depends(get_relation_agents)]
ChronicleAgentsDep: TypeAlias = Annotated[dict[str, Agent], Depends(get_chronicle_agents)]
