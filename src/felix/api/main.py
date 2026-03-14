from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from felix.agent.chat_agent import create_agent
from felix.agent.deps import FelixDeps
from felix.api.routes import characters, chat, ingest, timeline
from felix.config import settings
from felix.db.schema import init_db
from felix.vectorstore.store import get_collection

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    db = await init_db(str(settings.db_path))
    collection = get_collection()
    deps = FelixDeps(db=db, chroma_collection=collection)
    agent = create_agent(settings.llm_model, settings.llm_base_url)

    app.state.db = db
    app.state.deps = deps
    app.state.agent = agent
    app.state.model_name = settings.llm_model
    app.state.base_url = settings.llm_base_url

    print(f"Felix API started — model={settings.llm_model}, base_url={settings.llm_base_url}")
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
app.include_router(ingest.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "model": app.state.model_name,
        "base_url": app.state.base_url or "Mistral API",
    }


def cli() -> None:
    """Entry point for `felix-api` script — runs fastapi dev with reload."""
    import subprocess
    import sys

    subprocess.run(  # noqa: S603
        [sys.executable, "-m", "fastapi", "dev", "src/felix/api/main.py"],
        check=False,
    )


if __name__ == "__main__":
    cli()
