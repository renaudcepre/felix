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


def get_model_name(request: Request) -> str:
    return request.app.state.model_name


def get_base_url(request: Request) -> str | None:
    return request.app.state.base_url


def get_import_state(request: Request) -> ImportState:
    return request.app.state.import_state


Neo4jDriver: TypeAlias = Annotated[AsyncDriver, Depends(get_driver)]
Collection: TypeAlias = Annotated[chromadb.Collection, Depends(get_collection)]
ChatAgent: TypeAlias = Annotated[Agent, Depends(get_agent)]
ModelName: TypeAlias = Annotated[str, Depends(get_model_name)]
BaseUrl: TypeAlias = Annotated[str | None, Depends(get_base_url)]
ImportStateDep: TypeAlias = Annotated[ImportState, Depends(get_import_state)]
