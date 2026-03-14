from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic_ai.messages import ModelMessagesTypeAdapter

from felix.api.models import ChatRequest, ChatResponse, UsageInfo

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("")
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    agent = request.app.state.agent
    deps = request.app.state.deps

    message_history = None
    if body.message_history:
        message_history = ModelMessagesTypeAdapter.validate_python(
            body.message_history
        )

    result = await agent.run(
        body.message,
        deps=deps,
        message_history=message_history,
    )

    serialized = ModelMessagesTypeAdapter.dump_python(
        result.all_messages(), mode="json"
    )

    usage = result.usage()
    usage_info = UsageInfo(
        request_tokens=usage.request_tokens or 0,
        response_tokens=usage.response_tokens or 0,
        total_tokens=usage.total_tokens or 0,
    )

    return ChatResponse(
        output=result.output,
        message_history=serialized,
        usage=usage_info,
    )
