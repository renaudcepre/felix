from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import chromadb
    from neo4j import AsyncDriver

    from felix.ingest.models import SceneAnalysis

from pydantic_ai.exceptions import ModelHTTPError
from rapidfuzz import fuzz

from felix.config import SCENE_FILE_EXTENSIONS, settings
from felix.graph.checks import check_bilocalization
from felix.graph.repository import (
    add_character_alias,
    add_location_alias,
    create_issue,
    delete_issues_for_scenes,
    get_character_profile,
    get_relation_types_for_pair,
    get_scene_ids_for_stems,
    list_all_characters_full,
    list_all_locations,
    patch_character_profile_fields,
    update_character_profile,
    upsert_character_relation,
)
from felix.graph.writer import delete_scenes, link_next_chunk, write_scene
from felix.ingest.analyzer import analyze_scene, create_analyzer_agent
from felix.ingest.checker import check_scene_consistency, create_checker_agents
from felix.ingest.loader import load_scene
from felix.ingest.profiler import (
    create_profiler_agent,
    create_profiler_patch_agent,
    patch_character_profile,
    profile_character,
)
from felix.ingest.resolver import (
    AmbiguousMatch,
    ResolvedEntity,
    fuzzy_match_entity,
    slugify,
)
from felix.ingest.segmenter import TextSegmenter

logger = logging.getLogger("felix.ingest")

EventQueue = asyncio.Queue[dict[str, Any]]

CLARIFICATION_TIMEOUT = 30.0


class ImportStatus(StrEnum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    RESOLVING = "resolving"
    LOADING = "loading"
    CHECKING = "checking"
    PROFILING = "profiling"
    DONE = "done"
    ERROR = "error"


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
class ClarificationSlot:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    answer: str = ""


async def _emit(queue: EventQueue, event: str, **data: Any) -> None:
    await queue.put({"event": event, **data})


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
) -> tuple[dict[str, str], dict[str, list[str]], dict[str, str], dict[str, list[str]], dict[str, dict]]:
    chars = await list_all_characters_full(driver)
    locs = await list_all_locations(driver)

    char_details: dict[str, dict] = {
        c["id"]: {
            "era": c.get("era"),
            "background": c.get("background"),
            "status": c.get("status"),
        }
        for c in chars
    }

    char_registry, char_aliases, loc_registry, loc_aliases = _build_registry(chars, locs)
    return char_registry, char_aliases, loc_registry, loc_aliases, char_details


_EXCERPT_MAX_LEN = 120


def _find_excerpt(name: str, scene_text: str) -> str | None:
    """Return the first line of scene_text that contains the name (case-insensitive)."""
    for line in scene_text.splitlines():
        if name.lower() in line.lower() and line.strip():
            excerpt = line.strip()
            return excerpt[:_EXCERPT_MAX_LEN] + "…" if len(excerpt) > _EXCERPT_MAX_LEN else excerpt
    return None


async def _resolve_characters(  # noqa: PLR0913
    analysis: SceneAnalysis,
    scene_text: str,
    char_registry: dict[str, str],
    char_aliases: dict[str, list[str]],
    char_details: dict[str, dict],
    scene_id: str,
    issues: list[dict],
    driver: AsyncDriver,
    queue: EventQueue | None = None,
    pending_clarifications: dict[str, ClarificationSlot] | None = None,
) -> list[tuple[ResolvedEntity, str, str | None]]:
    resolved_chars: list[tuple[ResolvedEntity, str, str | None]] = []
    for ec in analysis.characters:
        match = fuzzy_match_entity(ec.name, char_registry, char_aliases)
        if isinstance(match, AmbiguousMatch):
            context = ec.description or _find_excerpt(ec.name, scene_text)
            resolved = await _handle_ambiguous_character(
                ec.name,
                context,
                match,
                char_details,
                scene_id,
                issues,
                queue,
                pending_clarifications,
                char_registry,
                char_aliases,
                driver,
            )
        else:
            resolved = match
            if resolved.is_new:
                char_registry[resolved.id] = resolved.name
            if queue:
                action = "created" if resolved.is_new else "linked"
                await _emit(
                    queue,
                    "entity_resolved",
                    name=ec.name,
                    action=action,
                    linked_to=resolved.name if not resolved.is_new else None,
                    score=round(resolved.score, 2) if resolved.score is not None else None,
                )
        resolved_chars.append((resolved, ec.role, ec.description))
    return resolved_chars


async def _handle_ambiguous_character(  # noqa: PLR0913
    name: str,
    context: str | None,
    match: AmbiguousMatch,
    char_details: dict[str, dict],
    scene_id: str,
    issues: list[dict],
    queue: EventQueue | None,
    pending_clarifications: dict[str, ClarificationSlot] | None,
    char_registry: dict[str, str],
    char_aliases: dict[str, list[str]],
    driver: AsyncDriver,
) -> ResolvedEntity:
    if queue and pending_clarifications is not None:
        clarification_id = str(uuid.uuid4())
        slot = ClarificationSlot()
        pending_clarifications[clarification_id] = slot

        candidate_info = char_details.get(match.best_id, {})
        await _emit(
            queue,
            "clarification_needed",
            id=clarification_id,
            question=f"'{name}' = '{match.best_name}' ?",
            entity_name=name,
            entity_context=context,
            candidate_name=match.best_name,
            candidate_id=match.best_id,
            candidate_era=candidate_info.get("era"),
            candidate_background=candidate_info.get("background"),
            score=round(match.score, 2),
            options=["link", "new"],
        )

        try:
            await asyncio.wait_for(slot.event.wait(), timeout=CLARIFICATION_TIMEOUT)
        except TimeoutError:
            slot.answer = "link"
        finally:
            pending_clarifications.pop(clarification_id, None)

        if slot.answer == "new":
            new_id = slugify(name)
            resolved = ResolvedEntity(id=new_id, name=name, is_new=True)
            char_registry[new_id] = name
            issues.append({
                "id": str(uuid.uuid4()),
                "type": "duplicate_suspect",
                "severity": "info",
                "scene_id": scene_id,
                "entity_id": new_id,
                "description": (
                    f"Personnage '{name}' confirme comme distinct de '{match.best_name}' "
                    f"(score {match.score:.2f}). Nouvelle entite creee."
                ),
                "suggestion": None,
            })
            await _emit(queue, "entity_resolved", name=name, action="created")
            return resolved

        was_timeout = slot.answer == "link" and not slot.event.is_set()
        if not was_timeout:
            char_aliases.setdefault(match.best_id, []).append(name)
            await add_character_alias(driver, match.best_id, name)
        issues.append({
            "id": str(uuid.uuid4()),
            "type": "duplicate_suspect",
            "severity": "warning",
            "scene_id": scene_id,
            "entity_id": match.best_id,
            "resolved": not was_timeout,
            "description": (
                f"Personnage '{name}' ressemble a '{match.best_name}' "
                f"(score {match.score:.2f}). Lien "
                + ("automatique (timeout)" if was_timeout else "confirme par l'utilisateur")
                + "."
            ),
            "suggestion": f"Verifier si '{name}' est bien '{match.best_name}'."
            if was_timeout
            else None,
        })
        await _emit(
            queue,
            "entity_resolved",
            name=name,
            action="linked",
            linked_to=match.best_name,
            score=round(match.score, 2),
        )
        return ResolvedEntity(id=match.best_id, name=match.best_name)

    # Fallback: no queue, auto-link
    issues.append({
        "id": str(uuid.uuid4()),
        "type": "duplicate_suspect",
        "severity": "warning",
        "scene_id": scene_id,
        "entity_id": match.best_id,
        "description": (
            f"Personnage '{name}' ressemble a '{match.best_name}' "
            f"(score {match.score:.2f}). Lien automatique effectue."
        ),
        "suggestion": f"Verifier si '{name}' est bien '{match.best_name}'.",
    })
    return ResolvedEntity(id=match.best_id, name=match.best_name)


async def _resolve_location(  # noqa: PLR0913
    analysis: SceneAnalysis,
    loc_registry: dict[str, str],
    loc_aliases: dict[str, list[str]],
    driver: AsyncDriver,
    scene_id: str,
    issues: list[dict],
    queue: EventQueue | None = None,
    pending_clarifications: dict[str, ClarificationSlot] | None = None,
) -> ResolvedEntity:
    match = fuzzy_match_entity(analysis.location.name, loc_registry, loc_aliases)
    if isinstance(match, AmbiguousMatch):
        if queue and pending_clarifications is not None:
            clarification_id = str(uuid.uuid4())
            slot = ClarificationSlot()
            pending_clarifications[clarification_id] = slot

            await _emit(
                queue,
                "clarification_needed",
                id=clarification_id,
                question=f"Lieu '{analysis.location.name}' = '{match.best_name}' ?",
                entity_name=analysis.location.name,
                candidate_name=match.best_name,
                candidate_id=match.best_id,
                score=round(match.score, 2),
                options=["link", "new"],
            )

            try:
                await asyncio.wait_for(slot.event.wait(), timeout=CLARIFICATION_TIMEOUT)
            except TimeoutError:
                slot.answer = "link"
            finally:
                pending_clarifications.pop(clarification_id, None)

            if slot.answer == "new":
                new_id = slugify(analysis.location.name)
                loc_registry[new_id] = analysis.location.name
                await _emit(queue, "entity_resolved", name=analysis.location.name, action="created")
                return ResolvedEntity(id=new_id, name=analysis.location.name, is_new=True)

            was_timeout = slot.answer == "link" and not slot.event.is_set()
            if not was_timeout:
                loc_aliases.setdefault(match.best_id, []).append(analysis.location.name)
                await add_location_alias(driver, match.best_id, analysis.location.name)
            issues.append({
                "id": str(uuid.uuid4()),
                "type": "duplicate_suspect",
                "severity": "warning",
                "scene_id": scene_id,
                "entity_id": match.best_id,
                "resolved": not was_timeout,
                "description": (
                    f"Lieu '{analysis.location.name}' ressemble a '{match.best_name}' "
                    f"(score {match.score:.2f}). Lien effectue."
                ),
                "suggestion": None,
            })
            await _emit(
                queue,
                "entity_resolved",
                name=analysis.location.name,
                action="linked",
                linked_to=match.best_name,
                score=round(match.score, 2),
            )
            return ResolvedEntity(id=match.best_id, name=match.best_name)

        # Fallback: no queue
        issues.append({
            "id": str(uuid.uuid4()),
            "type": "duplicate_suspect",
            "severity": "warning",
            "scene_id": scene_id,
            "entity_id": match.best_id,
            "description": (
                f"Lieu '{analysis.location.name}' ressemble a '{match.best_name}' "
                f"(score {match.score:.2f}). Lien automatique effectue."
            ),
            "suggestion": f"Verifier si '{analysis.location.name}' est bien '{match.best_name}'.",
        })
        return ResolvedEntity(id=match.best_id, name=match.best_name)

    if match.is_new:
        loc_registry[match.id] = match.name
    if queue:
        action = "created" if match.is_new else "linked"
        await _emit(
            queue,
            "entity_resolved",
            name=analysis.location.name,
            action=action,
            linked_to=match.name if not match.is_new else None,
        )
    return match


@dataclass
class _PipelineContext:
    driver: AsyncDriver
    collection: chromadb.Collection
    progress: ImportProgress
    queue: EventQueue | None
    pending_clarifications: dict[str, ClarificationSlot] | None
    char_registry: dict[str, str] = field(default_factory=dict)
    char_aliases: dict[str, list[str]] = field(default_factory=dict)
    loc_registry: dict[str, str] = field(default_factory=dict)
    loc_aliases: dict[str, list[str]] = field(default_factory=dict)
    char_details: dict[str, dict] = field(default_factory=dict)


def _make_scene_id(stem: str, chunk_idx: int, total_chunks: int) -> str:
    if total_chunks == 1:
        return f"scene-{stem}"
    return f"scene-{stem}-chunk-{chunk_idx:02d}"


async def _emit_status(ctx: _PipelineContext, status: ImportStatus) -> None:
    if ctx.queue:
        await _emit(
            ctx.queue,
            "status_change",
            status=status,
            current_scene=ctx.progress.current_scene,
            processed_scenes=ctx.progress.processed_scenes,
            total_scenes=ctx.progress.total_scenes,
        )


async def _process_scene(
    ctx: _PipelineContext,
    scene_file: Path,
    analyzer: Any,
    *,
    scene_id: str | None = None,
    chunk_text: str | None = None,
) -> tuple[list[dict], dict, list[tuple[Any, str, str | None]], str]:
    if scene_id is None:
        scene_id = f"scene-{scene_file.stem}"
    ctx.progress.current_scene = scene_file.name
    ctx.progress.status = ImportStatus.ANALYZING
    await _emit_status(ctx, ImportStatus.ANALYZING)

    if chunk_text is not None:
        scene_text = chunk_text
    else:
        scene_text = await asyncio.to_thread(scene_file.read_text, encoding="utf-8")
    analysis = await analyze_scene(analyzer, scene_text)

    if ctx.queue:
        await _emit(
            ctx.queue,
            "scene_analyzed",
            scene_id=scene_id,
            title=analysis.title,
            summary=analysis.summary,
            characters=[{"name": c.name, "role": c.role} for c in analysis.characters],
            location=analysis.location.name,
            era=analysis.era,
            date=analysis.approximate_date,
            mood=analysis.mood,
        )

    ctx.progress.status = ImportStatus.RESOLVING
    await _emit_status(ctx, ImportStatus.RESOLVING)
    scene_issues: list[dict] = []

    resolved_chars = await _resolve_characters(
        analysis,
        scene_text,
        ctx.char_registry,
        ctx.char_aliases,
        ctx.char_details,
        scene_id,
        scene_issues,
        ctx.driver,
        ctx.queue,
        ctx.pending_clarifications,
    )
    resolved_location = await _resolve_location(
        analysis,
        ctx.loc_registry,
        ctx.loc_aliases,
        ctx.driver,
        scene_id,
        scene_issues,
        ctx.queue,
        ctx.pending_clarifications,
    )

    for rc, _, _ in resolved_chars:
        if rc.is_new:
            ctx.progress.new_characters.append(rc.name)
    if resolved_location.is_new:
        ctx.progress.new_locations.append(resolved_location.name)

    ctx.progress.status = ImportStatus.LOADING
    await _emit_status(ctx, ImportStatus.LOADING)
    await load_scene(
        ctx.driver,
        ctx.collection,
        scene_id,
        scene_file.name,
        scene_text,
        analysis,
        resolved_chars,
        resolved_location,
    )

    if ctx.queue:
        await _emit(ctx.queue, "scene_loaded", scene_id=scene_id)

    summary = {
        "scene_id": scene_id,
        "title": analysis.title,
        "summary": analysis.summary,
        "era": analysis.era,
        "date": analysis.approximate_date,
        "characters": [
            {"name": rc.name, "id": rc.id, "role": role}
            for rc, role, _desc in resolved_chars
        ],
        "location": {"name": resolved_location.name, "id": resolved_location.id},
    }

    ctx.progress.processed_scenes += 1
    return scene_issues, summary, resolved_chars, scene_text


async def _check_scene(
    ctx: _PipelineContext,
    scene_summary: dict,
    timeline_agent: Any,
    narrative_agent: Any,
) -> None:
    ctx.progress.status = ImportStatus.CHECKING
    await _emit_status(ctx, ImportStatus.CHECKING)

    if ctx.queue:
        await _emit(
            ctx.queue,
            "check_started",
            scene_id=scene_summary["scene_id"],
            scene_title=scene_summary.get("title"),
        )

    try:
        report = await check_scene_consistency(
            ctx.driver, ctx.collection, scene_summary, timeline_agent, narrative_agent
        )
    except Exception as e:
        logger.exception("Consistency check failed for scene: %s", scene_summary["scene_id"])
        if ctx.queue:
            await _emit(ctx.queue, "consistency_error", error=str(e))
            await _emit(ctx.queue, "check_complete", issue_count=0)
        return

    for ci in report.issues:
        issue = {
            "id": str(uuid.uuid4()),
            "type": ci.type,
            "severity": ci.severity,
            "scene_id": ci.scene_id,
            "entity_id": ci.entity_id,
            "description": ci.description,
            "suggestion": ci.suggestion,
        }
        await create_issue(ctx.driver, issue)
        ctx.progress.issues_found += 1
        if ctx.queue:
            await _emit(
                ctx.queue,
                "issue_found",
                type=ci.type,
                severity=ci.severity,
                description=ci.description,
            )

    if ctx.queue:
        await _emit(ctx.queue, "check_complete", issue_count=len(report.issues))


async def _profile_scene_characters(  # noqa: PLR0912, PLR0913
    ctx: _PipelineContext,
    resolved_chars: list[tuple[Any, str, str | None]],
    scene_id: str,
    scene_text: str,
    scene_title: str,
    profiler: Any,
    profiler_patch: Any = None,
) -> None:
    ctx.progress.status = ImportStatus.PROFILING
    await _emit_status(ctx, ImportStatus.PROFILING)

    known_names = list(ctx.char_registry.values())

    for rc, role, desc in resolved_chars:
        if role == "mentioned":
            continue

        char_id = rc.id
        char_name = rc.name

        try:
            existing_row = await get_character_profile(ctx.driver, char_id)
            existing_profile = existing_row if existing_row else {}
            has_profile = bool(
                existing_profile.get("background") or existing_profile.get("arc")
            )

            fragment = {
                "scene_title": scene_title,
                "scene_id": scene_id,
                "role": role,
                "description": desc,
            }

            if ctx.queue:
                await _emit(ctx.queue, "profiling_character", name=char_name, id=char_id, scene_title=scene_title)

            char_known_names = [n for n in known_names if n != char_name]

            if has_profile:
                profile = await patch_character_profile(
                    profiler_patch or profiler, char_name, existing_profile, scene_text, fragment
                )
                await patch_character_profile_fields(ctx.driver, char_id, profile.model_dump())
            else:
                profile = await profile_character(
                    profiler, char_name, [scene_text], [fragment], char_known_names
                )
                await update_character_profile(ctx.driver, char_id, profile.model_dump())

            stored_relations: list[dict[str, str]] = []
            for rel in profile.relations:
                other_match = fuzzy_match_entity(
                    rel.other_name, ctx.char_registry, ctx.char_aliases
                )
                if isinstance(other_match, AmbiguousMatch):
                    other_id = other_match.best_id
                    other_name = other_match.best_name
                else:
                    if other_match.is_new:
                        continue
                    other_id = other_match.id
                    other_name = other_match.name
                if other_id != char_id:
                    a, b = sorted([char_id, other_id])
                    existing_rels = await get_relation_types_for_pair(ctx.driver, a, b)
                    is_duplicate = any(
                        fuzz.ratio(rel.relation.lower(), ex.lower()) >= 75  # noqa: PLR2004
                        for ex in existing_rels
                    )
                    if not is_duplicate:
                        era = existing_profile.get("era") or ctx.char_details.get(char_id, {}).get("era")
                        await upsert_character_relation(ctx.driver, a, b, rel.relation, era=era)
                        stored_relations.append({"other_name": other_name, "relation": rel.relation})

            filled = [
                k for k, v in profile.model_dump().items()
                if v and k in {"age", "physical", "background", "arc", "traits"}
            ]

            if ctx.queue:
                await _emit(
                    ctx.queue,
                    "character_profiled",
                    name=char_name,
                    id=char_id,
                    filled_fields=filled,
                    relations=stored_relations,
                )
        except Exception as e:
            logger.exception("Profiling failed for character: %s", char_name)
            if ctx.queue:
                await _emit(ctx.queue, "profiling_error", name=char_name, id=char_id, error=str(e))


async def run_import_pipeline(  # noqa: PLR0912, PLR0913, PLR0915
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
    )
    try:
        def _collect_scene_files() -> list[Path]:
            return sorted(
                f for ext in SCENE_FILE_EXTENSIONS for f in Path(scenes_dir).glob(f"*{ext}")
            )

        scene_files = await asyncio.to_thread(_collect_scene_files)
        if not scene_files:
            progress.error = f"Aucun fichier texte dans {scenes_dir}"
            progress.status = ImportStatus.ERROR
            if queue:
                await _emit(queue, "error", message=progress.error)
            return

        progress.total_scenes = len(scene_files)
        if queue:
            await _emit(
                queue,
                "status_change",
                status=ImportStatus.PENDING,
                total_scenes=progress.total_scenes,
                processed_scenes=0,
                current_scene="",
            )

        ctx.char_registry, ctx.char_aliases, ctx.loc_registry, ctx.loc_aliases, ctx.char_details = await _load_registries(driver)

        # Idempotent cleanup — covers both "scene-{stem}" and "scene-{stem}-chunk-NN"
        existing_scene_ids = await get_scene_ids_for_stems(driver, [f.stem for f in scene_files])
        await delete_issues_for_scenes(driver, existing_scene_ids)
        await delete_scenes(driver, existing_scene_ids)

        # Expand each file into (file, chunk_idx, total_chunks, chunk_text)
        segmenter = TextSegmenter(
            max_tokens=settings.segmenter_max_tokens,
            overlap_ratio=settings.segmenter_overlap_ratio,
            threshold=settings.segmenter_threshold,
        )
        scene_units: list[tuple[Path, int, int, str]] = []
        for scene_file in scene_files:
            raw_text = await asyncio.to_thread(scene_file.read_text, encoding="utf-8")
            chunks = await asyncio.to_thread(segmenter.segment, raw_text)
            if len(chunks) > 1 and queue:
                await _emit(queue, "file_segmented", filename=scene_file.name, chunk_count=len(chunks))
            for i, chunk in enumerate(chunks):
                scene_units.append((scene_file, i, len(chunks), chunk))

        progress.total_scenes = len(scene_units)
        if queue:
            await _emit(
                queue,
                "status_change",
                status=ImportStatus.PENDING,
                total_scenes=progress.total_scenes,
                processed_scenes=0,
                current_scene="",
            )

        analyzer = create_analyzer_agent(model_name, base_url)
        timeline_checker, narrative_checker = create_checker_agents(model_name, base_url)
        profiler = create_profiler_agent(model_name, base_url) if enrich_profiles else None
        profiler_patch = create_profiler_patch_agent(model_name, base_url) if enrich_profiles else None
        scenes_processed = 0

        for scene_file, chunk_idx, total_chunks, chunk_text in scene_units:
            scene_id = _make_scene_id(scene_file.stem, chunk_idx, total_chunks)
            try:
                scene_issues, summary, resolved_chars, _ = await _process_scene(
                    ctx, scene_file, analyzer, scene_id=scene_id, chunk_text=chunk_text
                )
                for issue in scene_issues:
                    await create_issue(driver, issue)
                progress.issues_found += len(scene_issues)
                scenes_processed += 1

                await _check_scene(ctx, summary, timeline_checker, narrative_checker)

                await write_scene(driver, summary)

                if chunk_idx > 0:
                    prev_id = _make_scene_id(scene_file.stem, chunk_idx - 1, total_chunks)
                    await link_next_chunk(driver, prev_id, scene_id)

                graph_issues = await check_bilocalization(driver, summary["scene_id"])
                for issue in graph_issues:
                    await create_issue(driver, issue)
                progress.issues_found += len(graph_issues)

                if enrich_profiles:
                    await _profile_scene_characters(
                        ctx,
                        resolved_chars,
                        summary["scene_id"],
                        chunk_text,
                        summary["title"],
                        profiler,
                        profiler_patch,
                    )
            except ModelHTTPError as e:
                logger.error("Scene processing failed: %s — HTTP %s: %s", scene_file.name, e.status_code, e)
                progress.failed_scenes += 1
                progress.processed_scenes += 1
                if queue:
                    await _emit(queue, "scene_error", scene_id=scene_id, filename=scene_file.name, error=str(e))
            except Exception as e:
                logger.exception("Scene processing failed: %s", scene_file.name)
                progress.failed_scenes += 1
                progress.processed_scenes += 1
                if queue:
                    await _emit(queue, "scene_error", scene_id=scene_id, filename=scene_file.name, error=str(e))

        if scenes_processed == 0:
            progress.error = f"Toutes les scenes ont echoue ({progress.failed_scenes}/{progress.total_scenes})"
            progress.status = ImportStatus.ERROR
            if queue:
                await _emit(queue, "error", message=progress.error)
            return

        progress.status = ImportStatus.DONE
        if queue:
            await _emit(
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
            await _emit(queue, "error", message=str(e))
    finally:
        await asyncio.to_thread(shutil.rmtree, scenes_dir, True)
