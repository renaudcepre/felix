from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from felix.ingest.pipeline import _PipelineContext
    from felix.ingest.resolution import EntityResolutionService

from felix.graph.repository import (
    create_issue,
    create_narrative_beat,
    get_character_profile,
    get_relation_types_for_pair,
    link_beat_character,
    patch_character_profile_fields,
    update_character_profile,
    upsert_character_relation,
)
from felix.ingest.analyzer import analyze_scene
from felix.ingest.checker import check_scene_consistency
from felix.ingest.loader import load_scene
from felix.ingest.models import NarrativeBeat
from felix.ingest.profiler import extract_scene_beats, patch_character_profile, profile_character
from felix.ingest.resolution import ImportStatus, _emit
from felix.ingest.resolver import AmbiguousMatch, fuzzy_match_entity
from rapidfuzz import fuzz

logger = logging.getLogger("felix.ingest")


def make_scene_id(stem: str, chunk_idx: int, total_chunks: int) -> str:
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


async def process_scene(
    ctx: _PipelineContext,
    resolver: EntityResolutionService,
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

    resolved_chars = await resolver.resolve_characters(analysis, scene_text, scene_id, scene_issues)
    resolved_location = await resolver.resolve_location(analysis, scene_id, scene_issues)

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


async def check_scene(
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


async def profile_scene_characters(  # noqa: PLR0912, PLR0913
    ctx: _PipelineContext,
    resolved_chars: list[tuple[Any, str, str | None]],
    scene_id: str,
    scene_text: str,
    scene_title: str,
    profiler: Any,
    profiler_patch: Any = None,
    beat_extractor: Any = None,
) -> None:
    ctx.progress.status = ImportStatus.PROFILING
    await _emit_status(ctx, ImportStatus.PROFILING)

    known_names = list(ctx.char_registry.values())

    # Extract narrative beats once per scene (1 LLM call)
    scene_beats: list[NarrativeBeat] = []
    if beat_extractor:
        active_names = [rc.name for rc, role, _ in resolved_chars if role != "mentioned"]
        if active_names:
            try:
                scene_beats = await extract_scene_beats(beat_extractor, scene_text, active_names)
                logger.debug("Scene %s — %d beats extracted", scene_id, len(scene_beats))
                # Store beats in Neo4j
                for i, beat in enumerate(scene_beats):
                    beat_id = f"{scene_id}-beat-{i}"
                    await create_narrative_beat(ctx.driver, beat_id, beat.action, scene_id)
                    # Resolve subject
                    subject_match = fuzzy_match_entity(beat.subject, ctx.char_registry, ctx.char_aliases)
                    subject_id: str | None = None
                    if not isinstance(subject_match, AmbiguousMatch) and not subject_match.is_new:
                        subject_id = subject_match.id
                        await link_beat_character(ctx.driver, beat_id, subject_id, "subject")
                    elif isinstance(subject_match, AmbiguousMatch):
                        subject_id = subject_match.best_id
                        await link_beat_character(ctx.driver, beat_id, subject_id, "subject")
                    # Resolve object
                    object_id: str | None = None
                    if beat.object:
                        object_match = fuzzy_match_entity(beat.object, ctx.char_registry, ctx.char_aliases)
                        if not isinstance(object_match, AmbiguousMatch) and not object_match.is_new:
                            object_id = object_match.id
                            await link_beat_character(ctx.driver, beat_id, object_id, "object")
                        elif isinstance(object_match, AmbiguousMatch):
                            object_id = object_match.best_id
                            await link_beat_character(ctx.driver, beat_id, object_id, "object")
                    logger.debug(
                        "  beat-%d: [%s] %s → %s → [%s] %s",
                        i,
                        beat.subject, subject_id or "?",
                        beat.action,
                        beat.object or "-", object_id or "-",
                    )
            except Exception:
                logger.exception("Beat extraction failed for scene: %s", scene_id)

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

            char_name_lower = char_name.lower()
            char_beats = [
                b for b in scene_beats
                if b.subject.lower() == char_name_lower
                or (b.object or "").lower() == char_name_lower
            ] or None

            if has_profile:
                profile = await patch_character_profile(
                    profiler_patch or profiler, char_name, existing_profile, scene_text, fragment,
                    beats=char_beats,
                )
                await patch_character_profile_fields(ctx.driver, char_id, profile.model_dump())
            else:
                profile = await profile_character(
                    profiler, char_name, [scene_text], [fragment], char_known_names,
                    beats=char_beats,
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
