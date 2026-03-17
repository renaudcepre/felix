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


def get_agent(request: Request) -> Agent:
    return request.app.state.agent


def get_model_name(request: Request) -> str:
    return request.app.state.model_name


def get_base_url(request: Request) -> str | None:
    return request.app.state.base_url


Neo4jDriver: TypeAlias = Annotated[AsyncDriver, Depends(get_driver)]
Collection: TypeAlias = Annotated[chromadb.Collection, Depends(get_collection)]
ChatAgent: TypeAlias = Annotated[Agent, Depends(get_agent)]
ModelName: TypeAlias = Annotated[str, Depends(get_model_name)]
BaseUrl: TypeAlias = Annotated[str | None, Depends(get_base_url)]
