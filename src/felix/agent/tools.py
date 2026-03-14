from __future__ import annotations

from pydantic_ai import RunContext

from felix.agent.deps import FelixDeps
from felix.db import queries
from felix.vectorstore.store import search_scenes_in_chroma


async def list_characters(ctx: RunContext[FelixDeps]) -> str:
    """List all characters in the screenplay bible.

    ALWAYS call this FIRST before calling get_character.
    Returns a list of character names and their IDs.
    Use the IDs from this list when calling get_character.
    """
    return await queries.list_characters(ctx.deps.db)


async def get_character(ctx: RunContext[FelixDeps], character_id: str) -> str:
    """Get the full profile of a specific character by their exact ID.

    You MUST call list_characters first to get valid IDs.

    Args:
        character_id: The exact character ID from list_characters (e.g. 'marie-dupont').
    """
    return await queries.get_character(ctx.deps.db, character_id)


async def list_locations(ctx: RunContext[FelixDeps]) -> str:
    """List all locations in the screenplay bible.

    ALWAYS call this FIRST before calling get_location.
    Returns a list of location names and their IDs.
    """
    return await queries.list_locations(ctx.deps.db)


async def get_location(ctx: RunContext[FelixDeps], location_id: str) -> str:
    """Get full details of a specific location by its exact ID.

    You MUST call list_locations first to get valid IDs.

    Args:
        location_id: The exact location ID from list_locations (e.g. 'lyon-safe-house').
    """
    return await queries.get_location(ctx.deps.db, location_id)


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
