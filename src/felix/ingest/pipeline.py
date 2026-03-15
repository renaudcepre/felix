from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiosqlite
    import chromadb

    from felix.ingest.models import SceneAnalysis

from felix.config import SCENE_FILE_EXTENSIONS
from rapidfuzz import fuzz

from felix.db.repository import (
    create_issue,
    delete_issues_for_scenes,
    get_character_fragments,
    get_relation_types_for_pair,
    update_character_profile,
    upsert_character_relation,
)
from felix.ingest.analyzer import analyze_scene, create_analyzer_agent
from felix.ingest.checker import check_consistency, create_checker_agent
from felix.ingest.loader import load_scene
from felix.ingest.profiler import create_profiler_agent, profile_character
from felix.ingest.resolver import (
    AmbiguousMatch,
    ResolvedEntity,
    fuzzy_match_entity,
    slugify,
)

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
) -> tuple[dict[str, str], dict[str, list[str]], dict[str, str]]:
    char_registry: dict[str, str] = {}
    char_aliases: dict[str, list[str]] = {}
    loc_registry: dict[str, str] = {}

    for c in db_chars:
        char_registry[c["id"]] = c["name"]
        aliases_raw = c.get("aliases")
        if aliases_raw:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                char_aliases[c["id"]] = json.loads(aliases_raw)

    for loc in db_locs:
        loc_registry[loc["id"]] = loc["name"]

    return char_registry, char_aliases, loc_registry


async def _load_registries(
    db: aiosqlite.Connection,
) -> tuple[dict[str, str], dict[str, list[str]], dict[str, str], dict[str, dict]]:
    cursor = await db.execute("SELECT id, name, aliases, era, background, status FROM characters")
    chars = [dict(row) for row in await cursor.fetchall()]

    cursor = await db.execute("SELECT id, name FROM locations")
    locs = [dict(row) for row in await cursor.fetchall()]

    char_details: dict[str, dict] = {
        c["id"]: {
            "era": c.get("era"),
            "background": c.get("background"),
            "status": c.get("status"),
        }
        for c in chars
    }

    reg = _build_registry(chars, locs)
    return (*reg, char_details)


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
) -> ResolvedEntity:
    # If we have a queue and clarification support, ask the user
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
            slot.answer = "link"  # auto-resolve on timeout
        finally:
            pending_clarifications.pop(clarification_id, None)

        if slot.answer == "new":
            new_id = slugify(name)
            resolved = ResolvedEntity(id=new_id, name=name, is_new=True)
            char_registry[new_id] = name
            issues.append(
                {
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
                }
            )
            await _emit(
                queue,
                "entity_resolved",
                name=name,
                action="created",
            )
            return resolved

        # link (explicit or timeout)
        was_timeout = slot.answer == "link" and not slot.event.is_set()
        issues.append(
            {
                "id": str(uuid.uuid4()),
                "type": "duplicate_suspect",
                "severity": "warning",
                "scene_id": scene_id,
                "entity_id": match.best_id,
                "description": (
                    f"Personnage '{name}' ressemble a '{match.best_name}' "
                    f"(score {match.score:.2f}). Lien "
                    + (
                        "automatique (timeout)"
                        if was_timeout
                        else "confirme par l'utilisateur"
                    )
                    + "."
                ),
                "suggestion": f"Verifier si '{name}' est bien '{match.best_name}'."
                if was_timeout
                else None,
            }
        )
        await _emit(
            queue,
            "entity_resolved",
            name=name,
            action="linked",
            linked_to=match.best_name,
            score=round(match.score, 2),
        )
        return ResolvedEntity(id=match.best_id, name=match.best_name)

    # Fallback: no queue, auto-link like before
    issues.append(
        {
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
        }
    )
    return ResolvedEntity(id=match.best_id, name=match.best_name)


async def _resolve_location(  # noqa: PLR0913
    analysis: SceneAnalysis,
    loc_registry: dict[str, str],
    scene_id: str,
    issues: list[dict],
    queue: EventQueue | None = None,
    pending_clarifications: dict[str, ClarificationSlot] | None = None,
) -> ResolvedEntity:
    match = fuzzy_match_entity(analysis.location.name, loc_registry)
    if isinstance(match, AmbiguousMatch):
        # For locations, ask user if queue available
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
                await _emit(
                    queue,
                    "entity_resolved",
                    name=analysis.location.name,
                    action="created",
                )
                return ResolvedEntity(
                    id=new_id, name=analysis.location.name, is_new=True
                )

            # link
            issues.append(
                {
                    "id": str(uuid.uuid4()),
                    "type": "duplicate_suspect",
                    "severity": "warning",
                    "scene_id": scene_id,
                    "entity_id": match.best_id,
                    "description": (
                        f"Lieu '{analysis.location.name}' ressemble a '{match.best_name}' "
                        f"(score {match.score:.2f}). Lien effectue."
                    ),
                    "suggestion": None,
                }
            )
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
        issues.append(
            {
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
            }
        )
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
    db: aiosqlite.Connection
    collection: chromadb.Collection
    progress: ImportProgress
    queue: EventQueue | None
    pending_clarifications: dict[str, ClarificationSlot] | None
    char_registry: dict[str, str] = field(default_factory=dict)
    char_aliases: dict[str, list[str]] = field(default_factory=dict)
    loc_registry: dict[str, str] = field(default_factory=dict)
    char_details: dict[str, dict] = field(default_factory=dict)


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
) -> tuple[list[dict], dict]:
    scene_id = f"scene-{scene_file.stem}"
    ctx.progress.current_scene = scene_file.name
    ctx.progress.status = ImportStatus.ANALYZING
    await _emit_status(ctx, ImportStatus.ANALYZING)

    scene_text = scene_file.read_text(encoding="utf-8")  # noqa: ASYNC240
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

    # Resolve
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
        ctx.queue,
        ctx.pending_clarifications,
    )
    resolved_location = await _resolve_location(
        analysis,
        ctx.loc_registry,
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

    # Load
    ctx.progress.status = ImportStatus.LOADING
    await _emit_status(ctx, ImportStatus.LOADING)
    await load_scene(
        ctx.db,
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
    return scene_issues, summary


async def _run_consistency_check(
    ctx: _PipelineContext,
    scenes_summary: list[dict],
    model_name: str | None,
    base_url: str | None,
) -> list[dict]:
    ctx.progress.status = ImportStatus.CHECKING
    ctx.progress.current_scene = ""
    await _emit_status(ctx, ImportStatus.CHECKING)

    if ctx.queue:
        await _emit(
            ctx.queue,
            "check_started",
            scene_count=len(scenes_summary),
        )

    checker = create_checker_agent(model_name, base_url)
    report = await check_consistency(checker, scenes_summary)

    issues: list[dict] = []
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
        issues.append(issue)
        if ctx.queue:
            await _emit(
                ctx.queue,
                "issue_found",
                type=ci.type,
                severity=ci.severity,
                description=ci.description,
            )

    if ctx.queue:
        await _emit(
            ctx.queue,
            "check_complete",
            issue_count=len(issues),
        )

    return issues


async def _run_character_profiling(
    ctx: _PipelineContext,
    model_name: str | None,
    base_url: str | None,
) -> None:
    ctx.progress.status = ImportStatus.PROFILING
    ctx.progress.current_scene = ""
    await _emit_status(ctx, ImportStatus.PROFILING)

    # Find characters with at least 1 fragment
    cursor = await ctx.db.execute(
        """
        SELECT DISTINCT c.id, c.name, c.era
        FROM characters c
        JOIN character_fragments cf ON c.id = cf.character_id
        ORDER BY c.name
        """
    )
    chars = [dict(row) for row in await cursor.fetchall()]
    if not chars:
        return

    profiler = create_profiler_agent(model_name, base_url)

    for char in chars:
        char_id = char["id"]
        char_name = char["name"]

        try:
            # Fetch fragments
            fragments = await get_character_fragments(ctx.db, char_id)

            # Fetch scene texts from ChromaDB
            scene_ids = [f["scene_id"] for f in fragments]
            scene_texts: list[str] = []
            if scene_ids:
                results = ctx.collection.get(ids=scene_ids)
                scene_texts = results.get("documents") or []

            if ctx.queue:
                await _emit(
                    ctx.queue,
                    "profiling_character",
                    name=char_name,
                    id=char_id,
                    fragment_count=len(fragments),
                    scene_count=len(scene_texts),
                )

            known_names = [c["name"] for c in chars if c["id"] != char_id]
            profile = await profile_character(
                profiler, char_name, scene_texts, fragments, known_names
            )

            await update_character_profile(ctx.db, char_id, profile.model_dump())

            # Resolve and store relations
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
                        continue  # skip unknown characters
                    other_id = other_match.id
                    other_name = other_match.name
                if other_id != char_id:
                    a, b = sorted([char_id, other_id])
                    existing = await get_relation_types_for_pair(ctx.db, a, b)
                    is_duplicate = any(
                        fuzz.ratio(rel.relation.lower(), ex.lower()) >= 75
                        for ex in existing
                    )
                    if not is_duplicate:
                        await upsert_character_relation(
                            ctx.db, a, b, rel.relation, era=char.get("era")
                        )
                        stored_relations.append({
                            "other_name": other_name,
                            "relation": rel.relation,
                        })

            # Summary of filled fields
            filled = [
                k for k in ("age", "physical", "background", "arc", "traits")
                if getattr(profile, k)
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
                await _emit(
                    ctx.queue,
                    "profiling_error",
                    name=char_name,
                    id=char_id,
                    error=str(e),
                )


async def run_import_pipeline(  # noqa: PLR0912, PLR0913, PLR0915
    scenes_dir: str,
    db: aiosqlite.Connection,
    collection: chromadb.Collection,
    model_name: str | None,
    base_url: str | None,
    progress: ImportProgress,
    queue: EventQueue | None = None,
    pending_clarifications: dict[str, ClarificationSlot] | None = None,
    enrich_profiles: bool = True,
) -> None:
    ctx = _PipelineContext(
        db=db,
        collection=collection,
        progress=progress,
        queue=queue,
        pending_clarifications=pending_clarifications,
    )
    try:
        scene_files = sorted(
            f for ext in SCENE_FILE_EXTENSIONS for f in Path(scenes_dir).glob(f"*{ext}")  # noqa: ASYNC240
        )
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

        ctx.char_registry, ctx.char_aliases, ctx.loc_registry, ctx.char_details = await _load_registries(
            db
        )
        await delete_issues_for_scenes(db, [f"scene-{f.stem}" for f in scene_files])

        analyzer = create_analyzer_agent(model_name, base_url)
        all_issues: list[dict] = []
        scenes_summary: list[dict] = []

        for scene_file in scene_files:
            try:
                scene_issues, summary = await _process_scene(ctx, scene_file, analyzer)
                all_issues.extend(scene_issues)
                scenes_summary.append(summary)
            except Exception as e:
                logger.exception("Scene analysis failed: %s", scene_file.name)
                progress.failed_scenes += 1
                progress.processed_scenes += 1
                if queue:
                    await _emit(
                        queue,
                        "scene_error",
                        scene_id=f"scene-{scene_file.stem}",
                        filename=scene_file.name,
                        error=str(e),
                    )

        if not scenes_summary:
            progress.error = f"Toutes les scenes ont echoue ({progress.failed_scenes}/{progress.total_scenes})"
            progress.status = ImportStatus.ERROR
            if queue:
                await _emit(queue, "error", message=progress.error)
            return

        try:
            check_issues = await _run_consistency_check(
                ctx, scenes_summary, model_name, base_url
            )
            all_issues.extend(check_issues)
        except Exception as e:
            logger.exception("Consistency check failed")
            if queue:
                await _emit(queue, "consistency_error", error=str(e))

        for issue in all_issues:
            await create_issue(db, issue)

        progress.issues_found = len(all_issues)

        if enrich_profiles:
            await _run_character_profiling(ctx, model_name, base_url)

        progress.status = ImportStatus.DONE
        if queue:
            await _emit(
                queue,
                "done",
                total_issues=len(all_issues),
                new_characters=progress.new_characters,
                new_locations=progress.new_locations,
            )

    except Exception as e:
        logger.exception("Import pipeline failed")
        progress.error = str(e)
        progress.status = ImportStatus.ERROR
        if queue:
            await _emit(queue, "error", message=str(e))
