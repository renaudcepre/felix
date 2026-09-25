from __future__ import annotations

from typing import Annotated, TypeAlias

import chromadb
from fastapi import Depends, Request
from neo4j import AsyncDriver
from pydantic_ai import Agent

from felix.atelier.agent import RouteDecision
from felix.core import GenericDeps


def get_driver(request: Request) -> AsyncDriver:
    driver: AsyncDriver = request.app.state.driver
    return driver


def get_collection(request: Request) -> chromadb.Collection:
    collection: chromadb.Collection = request.app.state.collection
    return collection


def get_gate_agents(request: Request) -> dict[str, Agent[None, RouteDecision]]:
    """Gates de routage stateless (RouteDecision) pré-construits PAR PROFIL : la
    question posée au gate (fait de récit ? fait technique ?) dépend du domaine,
    comme le maître et les extracteurs. Appelé avec le message SEUL, jamais
    d'historique."""
    gate_agents: dict[str, Agent[None, RouteDecision]] = request.app.state.gate_agents
    return gate_agents


def get_master_agents(request: Request) -> dict[str, Agent[GenericDeps, str]]:
    """Agents « maître » (passe 0) pré-construits par profil : mènent la
    conversation (lecture seule, purement conversationnels)."""
    master_agents: dict[str, Agent[GenericDeps, str]] = request.app.state.master_agents
    return master_agents


def get_atelier_agents(request: Request) -> dict[str, Agent[GenericDeps, str]]:
    """Agents du bot B pré-construits par profil (scenario/chantier/none)."""
    atelier_agents: dict[str, Agent[GenericDeps, str]] = (
        request.app.state.atelier_agents
    )
    return atelier_agents


def get_relation_agents(request: Request) -> dict[str, Agent[GenericDeps, str]]:
    """Sous-agents « relieur » (2e passe) pré-construits par profil."""
    relation_agents: dict[str, Agent[GenericDeps, str]] = (
        request.app.state.relation_agents
    )
    return relation_agents


def get_chronicle_agents(request: Request) -> dict[str, Agent[GenericDeps, str]]:
    """Sous-agents « chroniqueur » (3e passe, événements) pré-construits par profil."""
    chronicle_agents: dict[str, Agent[GenericDeps, str]] = (
        request.app.state.chronicle_agents
    )
    return chronicle_agents


Neo4jDriver: TypeAlias = Annotated[AsyncDriver, Depends(get_driver)]
Collection: TypeAlias = Annotated[chromadb.Collection, Depends(get_collection)]
GateAgentsDep: TypeAlias = Annotated[
    dict[str, Agent[None, RouteDecision]], Depends(get_gate_agents)
]
MasterAgentsDep: TypeAlias = Annotated[
    dict[str, Agent[GenericDeps, str]], Depends(get_master_agents)
]
AtelierAgentsDep: TypeAlias = Annotated[
    dict[str, Agent[GenericDeps, str]], Depends(get_atelier_agents)
]
RelationAgentsDep: TypeAlias = Annotated[
    dict[str, Agent[GenericDeps, str]], Depends(get_relation_agents)
]
ChronicleAgentsDep: TypeAlias = Annotated[
    dict[str, Agent[GenericDeps, str]], Depends(get_chronicle_agents)
]
