from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from felix.config import settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ModelInfo(BaseModel):
    model_name: str
    base_url: str | None


@router.get("/model")
async def get_model() -> ModelInfo:
    return ModelInfo(
        model_name=settings.llm_model,
        base_url=settings.llm_base_url,
    )
