from __future__ import annotations

from pydantic_ai import RunContext

from felix.agent.deps import FelixDeps
from felix.graph import formatters
from felix.vectorstore.store import search_scenes_in_chroma


async def find_character(ctx: RunContext[FelixDeps], name: str) -> str:
    """Find a character by name or alias and return their full profile.

    Args:
        name: Full or partial character name (e.g. 'Marie', 'Renard', 'La Louve').
    """
    return await formatters.find_character(ctx.deps.driver, name)


async def find_location(ctx: RunContext[FelixDeps], name: str) -> str:
    """Find a location by name and return its full details.

    Args:
        name: Full or partial location name (e.g. 'Lyon', 'planque', 'Tribune').
    """
    return await formatters.find_location(ctx.deps.driver, name)


async def get_timeline(
    ctx: RunContext[FelixDeps],
    era: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    location: str | None = None,
) -> str:
    """Get timeline events, optionally filtered by era, date range, and/or location.

    All filters are optional. Omit date filters if the question is not date-specific.
    Use ISO date format (YYYY-MM-DD) for dates if provided.

    Args:
        era: Filter by era (e.g. '1940s', '1970s'). Optional.
        date_from: Start date inclusive (e.g. '1942-03-01'). Optional.
        date_to: End date inclusive (e.g. '1942-03-31'). Optional.
        location: Filter by location name (partial match, e.g. 'poste de relais', 'Lyon'). Optional.
    """
    return await formatters.get_timeline(
        ctx.deps.driver, era=era, date_from=date_from, date_to=date_to, location=location
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
