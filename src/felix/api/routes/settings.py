from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

from felix.agent.chat_agent import create_agent

router = APIRouter(prefix="/api/settings", tags=["settings"])

logger = logging.getLogger(__name__)


class ModelConfig(BaseModel):
    model_name: str
    base_url: str | None = None
    api_key: str | None = None


class ModelInfo(BaseModel):
    model_name: str
    base_url: str | None


@router.get("/model")
async def get_model(request: Request) -> ModelInfo:
    return ModelInfo(
        model_name=request.app.state.model_name,
        base_url=request.app.state.base_url,
    )


@router.put("/model")
async def set_model(body: ModelConfig, request: Request) -> ModelInfo:
    agent = create_agent(body.model_name, body.base_url, api_key=body.api_key)

    request.app.state.agent = agent
    request.app.state.model_name = body.model_name
    request.app.state.base_url = body.base_url

    logger.info("Model switched to %s (base_url=%s)", body.model_name, body.base_url)

    return ModelInfo(
        model_name=body.model_name,
        base_url=body.base_url,
    )
