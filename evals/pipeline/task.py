"""Task function wrapping the import pipeline for pydantic-evals.

The pipeline runs once on the fixture scenes via `build_pipeline_task()`,
which returns a closure capturing the initialized DB.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import chromadb
from pydantic import BaseModel
from rich.console import Console

from felix.db.schema import init_db
from felix.ingest.pipeline import ImportProgress, run_import_pipeline

_console = Console()

if TYPE_CHECKING:
    import aiosqlite
    from collections.abc import Callable, Coroutine

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class PipelineQueryResult(BaseModel):
    """Structured result for a pipeline DB query."""

    character_ids: list[str] = []
    location_names: list[str] = []
    issues: list[dict[str, Any]] = []
    background: str | None = None
    scene_date: str | None = None
    relations: list[dict[str, Any]] = []
    fragment_count: int = 0


async def _log_progress(progress: ImportProgress) -> None:
    """Affiche les changements de progress en temps réel."""
    last_scene = ""
    last_status = ""
    while True:
        scene = progress.current_scene
        status = str(progress.status)
        if scene != last_scene or status != last_status:
            if scene:
                n = progress.processed_scenes
                total = progress.total_scenes
                _console.print(f"  [dim][{n}/{total}][/dim] [cyan]{scene}[/cyan] — {status}")
            last_scene, last_status = scene, status
        await asyncio.sleep(0.3)


async def _run_pipeline() -> aiosqlite.Connection:
    """Run the import pipeline on fixtures, return the populated DB."""
    tmpdir = tempfile.mkdtemp()
    try:
        for f in sorted(FIXTURES_DIR.glob("*.txt")):
            shutil.copy(f, tmpdir)

        db = await init_db(":memory:")
        client = chromadb.EphemeralClient()
        collection = client.get_or_create_collection("pipeline_eval")
        progress = ImportProgress()

        poller = asyncio.create_task(_log_progress(progress))
        try:
            await run_import_pipeline(
                scenes_dir=tmpdir,
                db=db,
                collection=collection,
                model_name=os.environ.get("FLX_EVAL_MODEL"),
                base_url=os.environ.get("FLX_EVAL_BASE_URL", ""),
                progress=progress,
            )
        finally:
            poller.cancel()
            _console.print(f"  [green]✔[/green] Pipeline terminé — {progress.processed_scenes}/{progress.total_scenes} scènes, {progress.issues_found} issues")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return db


async def _query(db: aiosqlite.Connection, query: str) -> PipelineQueryResult:
    """Answer a DB query against an already-populated pipeline DB.

    Supported query keys:
      - "characters"               → character_ids list
      - "locations"                → location_names list
      - "irina_profile"            → background text for irina-voss
      - "irina_fragments"          → fragment_count for irina-voss
      - "profile:<char_id>"        → background text for any character
      - "fragments:<char_id>"      → fragment_count for any character (all roles)
      - "active_fragments:<char_id>" → fragment_count for participant role only
      - "relations"                → all character relations
      - "relations:<char_id>"      → relations involving a specific character
      - "issues:<scene_id>"        → issues for that scene
      - "all_issues"               → all issues across all scenes
      - "scene_date:<scene_id>"    → scene_date text for that scene
    """
    if query == "characters":
        cursor = await db.execute("SELECT id FROM characters")
        rows = await cursor.fetchall()
        return PipelineQueryResult(character_ids=[r[0] for r in rows])

    if query == "locations":
        cursor = await db.execute("SELECT name FROM locations")
        rows = await cursor.fetchall()
        return PipelineQueryResult(location_names=[r[0] for r in rows])

    if query == "irina_profile":
        cursor = await db.execute(
            "SELECT background, arc, traits FROM characters WHERE id = 'irina-voss'"
        )
        row = await cursor.fetchone()
        if row:
            parts = [v for v in (row[0], row[1], row[2]) if v]
            return PipelineQueryResult(background=" | ".join(parts) if parts else None)
        return PipelineQueryResult()

    if query.startswith("profile:"):
        char_id = query[len("profile:"):]
        cursor = await db.execute(
            "SELECT background, arc, traits FROM characters WHERE id = ?", (char_id,)
        )
        row = await cursor.fetchone()
        if row:
            parts = [v for v in (row[0], row[1], row[2]) if v]
            return PipelineQueryResult(background=" | ".join(parts) if parts else None)
        return PipelineQueryResult()

    if query == "irina_fragments":
        cursor = await db.execute(
            "SELECT COUNT(*) FROM character_fragments WHERE character_id = 'irina-voss'"
        )
        row = await cursor.fetchone()
        return PipelineQueryResult(fragment_count=row[0] if row else 0)

    if query.startswith("fragments:"):
        char_id = query[len("fragments:"):]
        cursor = await db.execute(
            "SELECT COUNT(*) FROM character_fragments WHERE character_id = ?", (char_id,)
        )
        row = await cursor.fetchone()
        return PipelineQueryResult(fragment_count=row[0] if row else 0)

    if query.startswith("active_fragments:"):
        char_id = query[len("active_fragments:"):]
        cursor = await db.execute(
            "SELECT COUNT(*) FROM character_fragments WHERE character_id = ? AND role = 'participant'",
            (char_id,),
        )
        row = await cursor.fetchone()
        return PipelineQueryResult(fragment_count=row[0] if row else 0)

    if query == "relations":
        cursor = await db.execute(
            "SELECT character_id_a, character_id_b, relation_type FROM character_relations"
        )
        rows = await cursor.fetchall()
        return PipelineQueryResult(relations=[{"a": r[0], "b": r[1], "relation": r[2]} for r in rows])

    if query.startswith("issues:"):
        scene_id = query[len("issues:"):]
        cursor = await db.execute(
            "SELECT type, severity, description FROM issues WHERE scene_id = ?",
            (scene_id,),
        )
        rows = await cursor.fetchall()
        return PipelineQueryResult(issues=[{"type": r[0], "severity": r[1], "description": r[2]} for r in rows])

    if query.startswith("relation_count:"):
        parts = query[len("relation_count:"):].split(",")
        if len(parts) == 2:  # noqa: PLR2004
            a, b = sorted(parts)
            cursor = await db.execute(
                "SELECT COUNT(*) FROM character_relations WHERE character_id_a = ? AND character_id_b = ?",
                (a, b),
            )
            row = await cursor.fetchone()
            return PipelineQueryResult(fragment_count=row[0] if row else 0)
        return PipelineQueryResult()

    if query.startswith("scene_date:"):
        scene_id = query[len("scene_date:"):]
        cursor = await db.execute("SELECT date FROM scenes WHERE id = ?", (scene_id,))
        row = await cursor.fetchone()
        return PipelineQueryResult(scene_date=row[0] if row else None)

    if query == "all_issues":
        cursor = await db.execute("SELECT type, severity, description, scene_id FROM issues")
        rows = await cursor.fetchall()
        return PipelineQueryResult(issues=[{"type": r[0], "severity": r[1], "description": r[2], "scene_id": r[3]} for r in rows])

    if query.startswith("relations:"):
        char_id = query[len("relations:"):]
        cursor = await db.execute(
            "SELECT character_id_a, character_id_b, relation_type FROM character_relations WHERE character_id_a = ? OR character_id_b = ?",
            (char_id, char_id),
        )
        rows = await cursor.fetchall()
        return PipelineQueryResult(relations=[{"a": r[0], "b": r[1], "relation": r[2]} for r in rows])

    return PipelineQueryResult()


async def build_pipeline_task() -> Callable[[str], Coroutine[Any, Any, PipelineQueryResult]]:
    """Initialize the pipeline and return a task closure capturing the DB."""
    db = await _run_pipeline()

    async def import_pipeline_task(query: str) -> PipelineQueryResult:
        return await _query(db, query)

    return import_pipeline_task
