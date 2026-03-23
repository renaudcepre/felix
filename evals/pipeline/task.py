"""Task function wrapping the import pipeline for pydantic-evals.

The pipeline runs once on the fixture scenes via `make_pipeline_task(subdir)`,
which returns a coroutine builder capturing the initialized driver.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import chromadb
from neo4j import AsyncDriver
from pydantic import BaseModel
from rich.console import Console

from felix.graph.driver import close_driver, get_driver, setup_constraints
from felix.graph.repositories.characters import (
    get_character_fragments,
    get_character_profile,
    get_relation_types_for_pair,
    list_all_character_relations,
    list_all_characters,
)
from felix.graph.repositories.groups import list_all_groups
from felix.graph.repositories.issues import list_issues
from felix.graph.repositories.locations import list_all_locations
from felix.graph.repositories.scenes import (
    count_next_chunk_links_for_stem,
    count_scenes_for_stem,
    get_scene_summaries_by_ids,
)
from felix.ingest.entity_checker import check_character_consistency
from felix.ingest.pipeline import ImportProgress, run_import_pipeline

_console = Console()

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures"


class PipelineQueryResult(BaseModel):
    """Structured result for a pipeline DB query."""

    character_ids: list[str] = []
    group_ids: list[str] = []
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


async def _run_pipeline(fixtures_dir: Path) -> AsyncDriver:
    """Run the import pipeline on fixtures, return the populated driver."""
    tmpdir = tempfile.mkdtemp()
    driver = get_driver()
    await setup_constraints(driver)

    # Clear any previous data (explicit write transaction for reliable commit)
    async def _delete_all(tx: Any) -> None:
        await tx.run("MATCH (n) DETACH DELETE n")

    async with driver.session() as session:
        await session.execute_write(_delete_all)
        # Verify the graph is actually empty
        result = await session.run("MATCH (n) RETURN count(n) AS remaining")
        record = await result.single()
        remaining = record["remaining"] if record else 0
        if remaining > 0:
            _console.print(f"  [yellow]Warning: {remaining} nodes still in DB after delete, retrying...[/yellow]")
            await session.execute_write(_delete_all)

    try:
        for f in sorted(fixtures_dir.glob("*.txt")):
            shutil.copy(f, tmpdir)

        client = chromadb.EphemeralClient()
        collection = client.get_or_create_collection("pipeline_eval")
        progress = ImportProgress()

        poller = asyncio.create_task(_log_progress(progress))
        try:
            await run_import_pipeline(
                scenes_dir=tmpdir,
                driver=driver,
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

    # Diagnostic: count nodes after pipeline to detect silent failures
    async with driver.session() as session:
        r = await session.run("MATCH (n) RETURN labels(n)[0] AS lbl, count(n) AS n ORDER BY lbl")
        rows = await r.data()
    if rows:
        counts = ", ".join(f"{row['lbl']}={row['n']}" for row in rows)
        _console.print(f"  [dim]Graph: {counts}[/dim]")
    else:
        _console.print("  [red]Graph: EMPTY — pipeline may have failed silently[/red]")

    return driver


async def _query(driver: AsyncDriver, query: str) -> PipelineQueryResult:  # noqa: PLR0911, PLR0912
    """Answer a DB query against an already-populated pipeline driver.

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
      - "relation_count:char_a,char_b" → relation count for a pair
      - "chunk_count:<stem>"           → number of Scene nodes for that file stem
      - "next_chunk_links:<stem>"      → number of NEXT_CHUNK links for that file stem
      - "traits:<char_id>"            → raw traits field for that character
      - "arc:<char_id>"               → raw arc field for that character
      - "age:<char_id>"               → raw age field for that character
      - "entity_check:<char_id>:<json>" → run entity consistency check, return issues
    """
    if query == "characters":
        rows = await list_all_characters(driver)
        return PipelineQueryResult(character_ids=[r["id"] for r in rows])

    if query == "groups":
        rows = await list_all_groups(driver)
        return PipelineQueryResult(group_ids=[r["id"] for r in rows])

    if query.startswith("member_of:"):
        char_id = query[len("member_of:"):]
        async with driver.session() as session:
            result = await session.run(
                "MATCH (c:Character {id: $id})-[:MEMBER_OF]->(g:Group) RETURN g.id AS id",
                id=char_id,
            )
            rows = await result.data()
        return PipelineQueryResult(group_ids=[r["id"] for r in rows])

    if query == "locations":
        rows = await list_all_locations(driver)
        return PipelineQueryResult(location_names=[r["name"] for r in rows])

    if query == "irina_profile":
        row = await get_character_profile(driver, "irina-voss")
        if row:
            parts = [v for v in (row.get("background"), row.get("arc"), row.get("traits")) if v]
            return PipelineQueryResult(background=" | ".join(parts) if parts else None)
        return PipelineQueryResult()

    if query.startswith("profile:"):
        char_id = query[len("profile:"):]
        row = await get_character_profile(driver, char_id)
        if row:
            parts = [v for v in (row.get("background"), row.get("arc"), row.get("traits")) if v]
            return PipelineQueryResult(background=" | ".join(parts) if parts else None)
        return PipelineQueryResult()

    if query == "irina_fragments":
        fragments = await get_character_fragments(driver, "irina-voss")
        return PipelineQueryResult(fragment_count=len(fragments))

    if query.startswith("fragments:"):
        char_id = query[len("fragments:"):]
        fragments = await get_character_fragments(driver, char_id)
        return PipelineQueryResult(fragment_count=len(fragments))

    if query.startswith("active_fragments:"):
        char_id = query[len("active_fragments:"):]
        fragments = await get_character_fragments(driver, char_id)
        return PipelineQueryResult(fragment_count=sum(1 for f in fragments if f.get("role") == "participant"))

    if query == "relations":
        rows = await list_all_character_relations(driver)
        return PipelineQueryResult(relations=[{"a": r["character_id_a"], "b": r["character_id_b"], "relation": r["relation_type"]} for r in rows])

    if query.startswith("issues:"):
        scene_id = query[len("issues:"):]
        all_issues = await list_issues(driver)
        filtered = [i for i in all_issues if i.get("scene_id") == scene_id]
        return PipelineQueryResult(issues=[{"type": i["type"], "severity": i["severity"], "description": i["description"]} for i in filtered])

    if query.startswith("relation_count:"):
        parts = query[len("relation_count:"):].split(",")
        if len(parts) == 2:  # noqa: PLR2004
            a, b = sorted(parts)
            rels = await get_relation_types_for_pair(driver, a, b)
            return PipelineQueryResult(fragment_count=len(rels))
        return PipelineQueryResult()

    if query.startswith("scene_date:"):
        scene_id = query[len("scene_date:"):]
        summaries = await get_scene_summaries_by_ids(driver, [scene_id])
        if summaries:
            return PipelineQueryResult(scene_date=summaries[0].get("date"))
        return PipelineQueryResult()

    if query == "all_issues":
        all_issues = await list_issues(driver)
        return PipelineQueryResult(issues=[{"type": i["type"], "severity": i["severity"], "description": i["description"], "scene_id": i.get("scene_id")} for i in all_issues])

    if query.startswith("relations:"):
        char_id = query[len("relations:"):]
        rows = await list_all_character_relations(driver)
        filtered = [r for r in rows if r["character_id_a"] == char_id or r["character_id_b"] == char_id]
        return PipelineQueryResult(relations=[{"a": r["character_id_a"], "b": r["character_id_b"], "relation": r["relation_type"]} for r in filtered])

    if query.startswith("traits:"):
        char_id = query[len("traits:"):]
        row = await get_character_profile(driver, char_id)
        return PipelineQueryResult(background=row.get("traits") if row else None)

    if query.startswith("arc:"):
        char_id = query[len("arc:"):]
        row = await get_character_profile(driver, char_id)
        return PipelineQueryResult(background=row.get("arc") if row else None)

    if query.startswith("age:"):
        char_id = query[len("age:"):]
        row = await get_character_profile(driver, char_id)
        return PipelineQueryResult(background=row.get("age") if row else None)

    if query.startswith("chunk_count:"):
        stem = query[len("chunk_count:"):]
        count = await count_scenes_for_stem(driver, stem)
        return PipelineQueryResult(fragment_count=count)

    if query.startswith("next_chunk_links:"):
        stem = query[len("next_chunk_links:"):]
        count = await count_next_chunk_links_for_stem(driver, stem)
        return PipelineQueryResult(fragment_count=count)

    if query.startswith("entity_check:"):
        rest = query[len("entity_check:"):]
        char_id, json_str = rest.split(":", 1)
        proposed = json.loads(json_str)
        model_name = os.environ.get("FLX_EVAL_MODEL")
        base_url = os.environ.get("FLX_EVAL_BASE_URL", "")
        report = await check_character_consistency(
            driver, char_id, proposed, model_name, base_url or None,
        )
        return PipelineQueryResult(
            issues=[
                {"type": i.type, "severity": i.severity, "description": i.description, "entity_id": i.entity_id}
                for i in report.issues
            ]
        )

    return PipelineQueryResult()


def make_pipeline_task(fixtures_subdir: str) -> Callable[[], Coroutine[Any, Any, Callable[[str], Coroutine[Any, Any, PipelineQueryResult]]]]:
    """Factory: returns an async no-arg builder that initializes the pipeline for the given fixtures subdir."""
    async def _builder() -> Callable[[str], Coroutine[Any, Any, PipelineQueryResult]]:
        drv = await _run_pipeline(FIXTURES_ROOT / fixtures_subdir)

        async def import_pipeline_task(query: str) -> PipelineQueryResult:
            return await _query(drv, query)

        return import_pipeline_task

    return _builder
