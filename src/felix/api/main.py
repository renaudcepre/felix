from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from felix.agent.chat_agent import create_agent
from felix.agent.deps import FelixDeps
from felix.api.routes import characters, chat, timeline
from felix.config import LMSTUDIO_DEFAULT_MODEL, LMSTUDIO_URL, settings
from felix.db.schema import init_db
from felix.vectorstore.store import get_collection

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

_startup_config: dict[str, str | None] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    model = _startup_config.get("model") or settings.felix_model
    base_url = _startup_config.get("base_url") or settings.felix_base_url

    db = await init_db(str(settings.db_path))
    collection = get_collection()
    deps = FelixDeps(db=db, chroma_collection=collection)
    agent = create_agent(model, base_url)

    app.state.db = db
    app.state.deps = deps
    app.state.agent = agent
    app.state.model_name = model
    app.state.base_url = base_url

    print(f"Felix API started — model={model}, base_url={base_url or 'Mistral API'}")
    yield

    await db.close()


app = FastAPI(title="Felix API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(characters.router)
app.include_router(timeline.router)
app.include_router(chat.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "model": app.state.model_name,
        "base_url": app.state.base_url or "Mistral API",
    }


def cli() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Felix API server")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--base-url", type=str, default=None)
    parser.add_argument("--local", action="store_true", help="Use LMStudio")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.local:
        _startup_config["base_url"] = args.base_url or LMSTUDIO_URL
        _startup_config["model"] = args.model or LMSTUDIO_DEFAULT_MODEL
    else:
        _startup_config["base_url"] = args.base_url
        _startup_config["model"] = args.model

    uvicorn.run(app, host="0.0.0.0", port=args.port)  # noqa: S104


if __name__ == "__main__":
    cli()
