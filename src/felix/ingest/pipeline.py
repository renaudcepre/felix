from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import chromadb
    from neo4j import AsyncDriver

from pydantic_ai.exceptions import ModelHTTPError

from felix.config import SCENE_FILE_EXTENSIONS, settings
from felix.graph.checks import check_bilocalization
from felix.graph.repositories.characters import list_all_characters_full
from felix.graph.repositories.groups import list_all_groups
from felix.graph.repositories.issues import create_issue, delete_issues_for_scenes
from felix.graph.repositories.locations import list_all_locations
from felix.graph.repositories.scenes import get_scene_ids_for_stems
from felix.graph.writer import delete_scenes, link_next_chunk, write_scene
from felix.ingest.analyzer import create_analyzer_agent
from felix.ingest.checker import create_checker_agents
from felix.ingest.cleaner import create_cleaner_agent
from felix.ingest.orchestrator import SceneOrchestrator, make_scene_id
from felix.ingest.profiler import (
    create_beat_extractor_agent,
    create_profiler_agent,
    create_profiler_patch_agent,
    create_relation_dedup_agent,
)
from felix.ingest.resolution import (
    ClarificationSlot,
    EntityResolutionService,
    EventQueue,
    ImportStatus,
    emit,
)
from felix.ingest.segmenter import TextSegmenter

logger = logging.getLogger("felix.ingest")


@dataclass
class ImportProgress:
    status: ImportStatus = ImportStatus.PENDING
    total_scenes: int = 0
    processed_scenes: int = 0
    failed_scenes: int = 0
    current_scene: str = ""
    issues_found: int = 0
    error: str = ""
    new_characters: list[str] = field(default_factory=list)
    new_locations: list[str] = field(default_factory=list)


@dataclass
class _PipelineContext:
    driver: AsyncDriver
    collection: chromadb.Collection
    progress: ImportProgress
    queue: EventQueue | None
    pending_clarifications: dict[str, ClarificationSlot] | None
    model_name: str | None = None
    base_url: str | None = None
    enrich_profiles: bool = True
    char_registry: dict[str, str] = field(default_factory=dict)
    char_aliases: dict[str, list[str]] = field(default_factory=dict)
    loc_registry: dict[str, str] = field(default_factory=dict)
    loc_aliases: dict[str, list[str]] = field(default_factory=dict)
    char_details: dict[str, dict] = field(default_factory=dict)
    group_registry: dict[str, str] = field(default_factory=dict)


def _build_registry(
    db_chars: list[dict], db_locs: list[dict]
) -> tuple[dict[str, str], dict[str, list[str]], dict[str, str], dict[str, list[str]]]:
    char_registry: dict[str, str] = {}
    char_aliases: dict[str, list[str]] = {}
    loc_registry: dict[str, str] = {}
    loc_aliases: dict[str, list[str]] = {}

    for c in db_chars:
        char_registry[c["id"]] = c["name"]
        aliases_raw = c.get("aliases")
        if aliases_raw and isinstance(aliases_raw, list):
            char_aliases[c["id"]] = aliases_raw

    for loc in db_locs:
        loc_registry[loc["id"]] = loc["name"]
        aliases_raw = loc.get("aliases")
        if aliases_raw and isinstance(aliases_raw, list):
            loc_aliases[loc["id"]] = aliases_raw

    return char_registry, char_aliases, loc_registry, loc_aliases


async def _load_registries(
    driver: AsyncDriver,
) -> tuple[dict[str, str], dict[str, list[str]], dict[str, str], dict[str, list[str]], dict[str, dict], dict[str, str]]:
    chars, locs, groups = await asyncio.gather(
        list_all_characters_full(driver),
        list_all_locations(driver),
        list_all_groups(driver),
    )

    char_details: dict[str, dict] = {
        c["id"]: {
            "era": c.get("era"),
            "background": c.get("background"),
            "status": c.get("status"),
        }
        for c in chars
    }

    char_registry, char_aliases, loc_registry, loc_aliases = _build_registry(chars, locs)
    group_registry: dict[str, str] = {g["id"]: g["name"] for g in groups}
    return char_registry, char_aliases, loc_registry, loc_aliases, char_details, group_registry


async def _segment_scene_files(
    scene_files: list[Path],
    queue: EventQueue | None,
) -> list[tuple[Path, int, int, str]]:
    """Segment each scene file into (file, chunk_idx, total_chunks, chunk_text) units."""
    if queue:
        await emit(queue, "status_change", status=ImportStatus.SEGMENTING, total_scenes=len(scene_files), processed_scenes=0, current_scene="")
    segmenter = TextSegmenter(
        max_tokens=settings.segmenter_max_tokens,
        overlap_ratio=settings.segmenter_overlap_ratio,
        threshold=settings.segmenter_threshold,
    )
    scene_units: list[tuple[Path, int, int, str]] = []
    for scene_file in scene_files:
        if queue:
            await emit(queue, "segmenting_file", filename=scene_file.name)
        raw_text = await asyncio.to_thread(scene_file.read_text, encoding="utf-8")
        chunks = await asyncio.to_thread(segmenter.segment, raw_text)
        if len(chunks) > 1 and queue:
            await emit(queue, "file_segmented", filename=scene_file.name, chunk_count=len(chunks))
        for i, chunk in enumerate(chunks):
            scene_units.append((scene_file, i, len(chunks), chunk))
    if queue:
        await emit(queue, "segmentation_complete", file_count=len(scene_files), scene_count=len(scene_units))
    return scene_units


def _create_agents(ctx: _PipelineContext) -> tuple:
    """Create all LLM agents needed by the pipeline."""
    analyzer = create_analyzer_agent(ctx.model_name, ctx.base_url)
    timeline_checker, narrative_checker = create_checker_agents(ctx.model_name, ctx.base_url)
    cleaner = create_cleaner_agent(ctx.model_name, ctx.base_url)
    profiler = create_profiler_agent(ctx.model_name, ctx.base_url) if ctx.enrich_profiles else None
    profiler_patch = create_profiler_patch_agent(ctx.model_name, ctx.base_url) if ctx.enrich_profiles else None
    beat_extractor = create_beat_extractor_agent(ctx.model_name, ctx.base_url) if ctx.enrich_profiles else None
    relation_deduper = create_relation_dedup_agent(ctx.model_name, ctx.base_url) if ctx.model_name else None
    return analyzer, timeline_checker, narrative_checker, cleaner, profiler, profiler_patch, beat_extractor, relation_deduper


async def _process_scene_unit(  # noqa: PLR0913
    ctx: _PipelineContext,
    orchestrator: SceneOrchestrator,
    scene_file: Path,
    scene_id: str,
    chunk_idx: int,
    total_chunks: int,
    chunk_text: str,
) -> None:
    """Process a single scene unit."""
    scene_issues, summary, resolved_chars, _ = await orchestrator.process_scene(
        scene_file, scene_id=scene_id, chunk_text=chunk_text
    )
    for issue in scene_issues:
        await create_issue(ctx.driver, issue)
    ctx.progress.issues_found += len(scene_issues)

    await orchestrator.check_scene(summary)
    await write_scene(ctx.driver, summary)

    if chunk_idx > 0:
        prev_id = make_scene_id(scene_file.stem, chunk_idx - 1, total_chunks)
        await link_next_chunk(ctx.driver, prev_id, scene_id)

    graph_issues = await check_bilocalization(ctx.driver, summary["scene_id"])
    for issue in graph_issues:
        await create_issue(ctx.driver, issue)
    ctx.progress.issues_found += len(graph_issues)

    if ctx.enrich_profiles:
        await orchestrator.profile_scene_characters(
            resolved_chars,
            summary["scene_id"],
            chunk_text,
            summary["title"],
        )


async def _process_all_scenes(
    ctx: _PipelineContext,
    orchestrator: SceneOrchestrator,
    scene_units: list[tuple[Path, int, int, str]],
) -> int:
    """Process all scene units, returning the number of successfully processed scenes."""
    scenes_processed = 0
    for scene_file, chunk_idx, total_chunks, chunk_text in scene_units:
        scene_id = make_scene_id(scene_file.stem, chunk_idx, total_chunks)
        try:
            await _process_scene_unit(
                ctx, orchestrator, scene_file, scene_id,
                chunk_idx, total_chunks, chunk_text,
            )
            scenes_processed += 1
        except ModelHTTPError as e:
            logger.error("Scene processing failed: %s — HTTP %s: %s", scene_file.name, e.status_code, e)
            ctx.progress.failed_scenes += 1
            ctx.progress.processed_scenes += 1
            if ctx.queue:
                await emit(ctx.queue, "scene_error", scene_id=scene_id, filename=scene_file.name, error=str(e))
        except Exception as e:
            logger.exception("Scene processing failed: %s", scene_file.name)
            ctx.progress.failed_scenes += 1
            ctx.progress.processed_scenes += 1
            if ctx.queue:
                await emit(ctx.queue, "scene_error", scene_id=scene_id, filename=scene_file.name, error=str(e))
    return scenes_processed


async def _setup_pipeline(
    ctx: _PipelineContext,
    scene_files: list[Path],
) -> tuple[SceneOrchestrator, list[tuple[Path, int, int, str]]]:
    """Load registries, clean up old data, segment files, and create the orchestrator."""
    ctx.char_registry, ctx.char_aliases, ctx.loc_registry, ctx.loc_aliases, ctx.char_details, ctx.group_registry = await _load_registries(ctx.driver)

    # Idempotent cleanup — covers both "scene-{stem}" and "scene-{stem}-chunk-NN"
    existing_scene_ids = await get_scene_ids_for_stems(ctx.driver, [f.stem for f in scene_files])
    await delete_issues_for_scenes(ctx.driver, existing_scene_ids)
    await delete_scenes(ctx.driver, existing_scene_ids)

    scene_units = await _segment_scene_files(scene_files, ctx.queue)

    ctx.progress.total_scenes = len(scene_units)
    if ctx.queue:
        await emit(
            ctx.queue,
            "status_change",
            status=ImportStatus.PENDING,
            total_scenes=ctx.progress.total_scenes,
            processed_scenes=0,
            current_scene="",
        )

    analyzer, timeline_checker, narrative_checker, cleaner, profiler, profiler_patch, beat_extractor, relation_deduper = _create_agents(ctx)

    resolver = EntityResolutionService(
        driver=ctx.driver,
        char_registry=ctx.char_registry,
        char_aliases=ctx.char_aliases,
        loc_registry=ctx.loc_registry,
        loc_aliases=ctx.loc_aliases,
        char_details=ctx.char_details,
        group_registry=ctx.group_registry,
        queue=ctx.queue,
        pending_clarifications=ctx.pending_clarifications,
    )
    orchestrator = SceneOrchestrator(
        ctx=ctx,
        resolver=resolver,
        analyzer=analyzer,
        timeline_checker=timeline_checker,
        narrative_checker=narrative_checker,
        profiler=profiler,
        profiler_patch=profiler_patch,
        beat_extractor=beat_extractor,
        cleaner=cleaner,
        relation_deduper=relation_deduper,
    )
    return orchestrator, scene_units


async def run_import_pipeline(  # noqa: PLR0913
    scenes_dir: str,
    driver: AsyncDriver,
    collection: chromadb.Collection,
    model_name: str | None,
    base_url: str | None,
    progress: ImportProgress,
    queue: EventQueue | None = None,
    pending_clarifications: dict[str, ClarificationSlot] | None = None,
    enrich_profiles: bool = True,
) -> None:
    ctx = _PipelineContext(
        driver=driver,
        collection=collection,
        progress=progress,
        queue=queue,
        pending_clarifications=pending_clarifications,
        model_name=model_name,
        base_url=base_url,
        enrich_profiles=enrich_profiles,
    )
    try:
        def _collect_scene_files() -> list[Path]:
            return sorted(
                f for ext in SCENE_FILE_EXTENSIONS for f in Path(scenes_dir).glob(f"*{ext}")
            )

        scene_files = await asyncio.to_thread(_collect_scene_files)
        if not scene_files:
            progress.error = f"No text files found in {scenes_dir}"
            progress.status = ImportStatus.ERROR
            if queue:
                await emit(queue, "error", message=progress.error)
            return

        progress.total_scenes = len(scene_files)
        if queue:
            await emit(
                queue,
                "status_change",
                status=ImportStatus.PENDING,
                total_scenes=progress.total_scenes,
                processed_scenes=0,
                current_scene="",
            )

        orchestrator, scene_units = await _setup_pipeline(ctx, scene_files)

        scenes_processed = await _process_all_scenes(ctx, orchestrator, scene_units)

        if scenes_processed == 0:
            progress.error = f"All scenes failed ({progress.failed_scenes}/{progress.total_scenes})"
            progress.status = ImportStatus.ERROR
            if queue:
                await emit(queue, "error", message=progress.error)
            return

        progress.status = ImportStatus.DONE
        if queue:
            await emit(
                queue,
                "done",
                total_issues=progress.issues_found,
                new_characters=progress.new_characters,
                new_locations=progress.new_locations,
            )

    except Exception as e:
        logger.exception("Import pipeline failed")
        progress.error = str(e)
        progress.status = ImportStatus.ERROR
        if queue:
            await emit(queue, "error", message=str(e))
    finally:
        await asyncio.to_thread(shutil.rmtree, scenes_dir, True)
