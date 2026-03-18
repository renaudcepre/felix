from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from felix.telemetry import setup_logfire

# Must be called before pydantic-ai imports so logfire can instrument the models.
setup_logfire()

from felix.agent.chat_agent import create_agent
from felix.api.deps import BaseUrl, ImportState, ModelName
from felix.api.routes import characters, chat, export, ingest, locations, timeline
from felix.config import settings
from felix.graph.driver import close_driver, get_driver, setup_constraints
from felix.vectorstore.store import get_collection

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    driver = get_driver()
    await setup_constraints(driver)
    collection = get_collection()
    agent = create_agent(settings.llm_model, settings.llm_base_url)

    app.state.driver = driver
    app.state.collection = collection
    app.state.agent = agent
    app.state.model_name = settings.llm_model
    app.state.base_url = settings.llm_base_url
    app.state.import_state = ImportState()

    print(f"Felix API started — model={settings.llm_model}, base_url={settings.llm_base_url}")
    yield

    await close_driver(driver)


app = FastAPI(title="Felix API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(characters.router)
app.include_router(locations.router)
app.include_router(timeline.router)
app.include_router(chat.router)
app.include_router(ingest.router)
app.include_router(export.router)


@app.get("/api/health")
async def health(model_name: ModelName, base_url: BaseUrl) -> dict[str, str]:
    return {
        "status": "ok",
        "model": model_name,
        "base_url": base_url or "Mistral API",
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
