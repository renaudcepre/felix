from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from pydantic_ai import Agent, FinalResultEvent, PartDeltaEvent, TextPartDelta
from pydantic_ai.messages import ModelMessagesTypeAdapter
from sse_starlette import EventSourceResponse, ServerSentEvent

from felix.api.models import ChatRequest, ChatResponse, UsageInfo

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("")
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    agent = request.app.state.agent
    deps = request.app.state.deps

    message_history = None
    if body.message_history:
        message_history = ModelMessagesTypeAdapter.validate_python(body.message_history)

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


@router.post("/stream")
async def chat_stream(body: ChatRequest, request: Request) -> EventSourceResponse:
    agent: Agent = request.app.state.agent
    deps = request.app.state.deps

    message_history = None
    if body.message_history:
        message_history = ModelMessagesTypeAdapter.validate_python(body.message_history)

    async def event_generator() -> AsyncGenerator[ServerSentEvent]:
        try:
            async with agent.iter(
                body.message, deps=deps, message_history=message_history
            ) as run:
                async for node in run:
                    if Agent.is_model_request_node(node):
                        async with node.stream(run.ctx) as request_stream:
                            async for event in request_stream:
                                if isinstance(event, PartDeltaEvent) and isinstance(
                                    event.delta, TextPartDelta
                                ):
                                    yield ServerSentEvent(
                                        data=event.delta.content_delta,
                                        event="content",
                                    )
                                elif isinstance(event, FinalResultEvent):
                                    break
                            # Stream remaining text after FinalResultEvent
                            async for text in request_stream.stream_text(delta=True):
                                yield ServerSentEvent(data=text, event="content")

                usage = run.usage()
                yield ServerSentEvent(
                    data=json.dumps(
                        {
                            "request_tokens": usage.request_tokens or 0,
                            "response_tokens": usage.response_tokens or 0,
                            "total_tokens": usage.total_tokens or 0,
                        }
                    ),
                    event="usage",
                )

                serialized = ModelMessagesTypeAdapter.dump_python(
                    run.all_messages(), mode="json"
                )
                yield ServerSentEvent(data=json.dumps(serialized), event="history")
                yield ServerSentEvent(data="", event="done")
        except Exception as e:
            yield ServerSentEvent(data=str(e), event="error")

    return EventSourceResponse(event_generator())
