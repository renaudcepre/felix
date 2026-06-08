from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from felix.telemetry import setup_logfire

logger = logging.getLogger(__name__)

# Must be called before pydantic-ai imports so logfire can instrument the models.
setup_logfire()

from felix.agent.chat_agent import create_agent
from felix.api.deps import ImportState
from felix.api.routes import atelier, characters, chat, checks, export, groups, ingest, locations, timeline
from felix.api.routes import settings as settings_routes
from felix.atelier.agent import (
    ATELIER_CHOICES,
    build_atelier_agent,
    build_chronicle_agent,
    build_relation_agent,
)
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
    agent = create_agent()

    app.state.driver = driver
    app.state.collection = collection
    app.state.agent = agent
    app.state.atelier_agents = {
        key: build_atelier_agent(choice) for key, choice in ATELIER_CHOICES.items()
    }
    app.state.relation_agents = {
        key: build_relation_agent(choice) for key, choice in ATELIER_CHOICES.items()
    }
    app.state.chronicle_agents = {
        key: build_chronicle_agent(choice) for key, choice in ATELIER_CHOICES.items()
    }
    app.state.import_state = ImportState()

    logger.info("Felix API started — model=%s, base_url=%s", settings.llm_model, settings.llm_base_url)
    yield

    await close_driver(driver)


app = FastAPI(title="Felix API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Dev local : le front peut se présenter en localhost, 127.0.0.1 ou [::1],
    # sur un port décalé si 3007 est occupé — on accepte toute origine locale.
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(characters.router)
app.include_router(checks.router)
app.include_router(groups.router)
app.include_router(locations.router)
app.include_router(timeline.router)
app.include_router(chat.router)
app.include_router(atelier.router)
app.include_router(ingest.router)
app.include_router(export.router)
app.include_router(settings_routes.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "model": settings.llm_model,
        "base_url": settings.llm_base_url or "Mistral API",
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
