from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Annotated, TypeAlias

import chromadb
from fastapi import Depends, Request
from neo4j import AsyncDriver
from pydantic_ai import Agent

from felix.ingest.pipeline import ClarificationSlot, ImportProgress


@dataclass
class ImportState:
    progress: ImportProgress | None = None
    task: asyncio.Task[None] | None = None
    pending_clarifications: dict[str, ClarificationSlot] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def get_driver(request: Request) -> AsyncDriver:
    return request.app.state.driver


def get_collection(request: Request) -> chromadb.Collection:
    return request.app.state.collection


def get_agent(request: Request) -> Agent:
    return request.app.state.agent


def get_atelier_agents(request: Request) -> dict[str, Agent]:
    """Agents du bot B pré-construits par profil (scenario/chantier/none)."""
    return request.app.state.atelier_agents


def get_relation_agents(request: Request) -> dict[str, Agent]:
    """Sous-agents « relieur » (2e passe) pré-construits par profil."""
    return request.app.state.relation_agents


def get_import_state(request: Request) -> ImportState:
    return request.app.state.import_state


Neo4jDriver: TypeAlias = Annotated[AsyncDriver, Depends(get_driver)]
Collection: TypeAlias = Annotated[chromadb.Collection, Depends(get_collection)]
ChatAgent: TypeAlias = Annotated[Agent, Depends(get_agent)]
AtelierAgentsDep: TypeAlias = Annotated[dict[str, Agent], Depends(get_atelier_agents)]
RelationAgentsDep: TypeAlias = Annotated[dict[str, Agent], Depends(get_relation_agents)]
ImportStateDep: TypeAlias = Annotated[ImportState, Depends(get_import_state)]
