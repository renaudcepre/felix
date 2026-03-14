from __future__ import annotations

from pydantic_ai import RunContext

from felix.agent.deps import FelixDeps
from felix.db import queries
from felix.vectorstore.store import search_scenes_in_chroma


async def find_character(ctx: RunContext[FelixDeps], name: str) -> str:
    """Find a character by name or alias and return their full profile.

    Args:
        name: Full or partial character name (e.g. 'Marie', 'Renard', 'La Louve').
    """
    return await queries.find_character(ctx.deps.db, name)


async def find_location(ctx: RunContext[FelixDeps], name: str) -> str:
    """Find a location by name and return its full details.

    Args:
        name: Full or partial location name (e.g. 'Lyon', 'planque', 'Tribune').
    """
    return await queries.find_location(ctx.deps.db, name)


async def get_timeline(
    ctx: RunContext[FelixDeps],
    era: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Get timeline events filtered by era and/or date range.

    IMPORTANT: Always provide date_from and date_to to avoid retrieving too many events.
    Use ISO date format: YYYY-MM-DD.

    Args:
        era: Filter by era (e.g. '1940s', '1970s'). Optional.
        date_from: Start date inclusive (e.g. '1942-03-01'). Strongly recommended.
        date_to: End date inclusive (e.g. '1942-03-31'). Strongly recommended.
    """
    return await queries.get_timeline(
        ctx.deps.db, era=era, date_from=date_from, date_to=date_to
    )


async def search_scenes(
    ctx: RunContext[FelixDeps],
    query: str,
    era: str | None = None,
    characters: list[str] | None = None,
) -> str:
    """Search scene text using semantic similarity.

    Use this when the writer asks about scene content, dialogue, or specific moments.

    Args:
        query: Natural language description of what to search for.
        era: Optional era filter (e.g. '1940s').
        characters: Optional list of character IDs to filter by (e.g. ['marie-dupont']).
    """
    return search_scenes_in_chroma(
        ctx.deps.chroma_collection,
        query=query,
        era=era,
        characters=characters,
    )
