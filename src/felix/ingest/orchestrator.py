from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from felix.ingest.pipeline import _PipelineContext
    from felix.ingest.resolution import EntityResolutionService

from felix.graph.repository import (
    create_issue,
    create_member_of,
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
from felix.ingest.cleaner import clean_scene_text
from felix.ingest.loader import load_scene
from felix.ingest.models import NarrativeBeat
from felix.ingest.profiler import extract_scene_beats, patch_character_profile, profile_character
from felix.ingest.resolution import CLARIFICATION_TIMEOUT, ClarificationSlot, ImportStatus, _emit, resolve_group_entity
from felix.ingest.resolver import AmbiguousMatch, fuzzy_match_entity
from rapidfuzz import fuzz

logger = logging.getLogger("felix.ingest")


async def _check_relation_semantic(
    deduper: Any,
    char_a: str,
    char_b: str,
    existing: str,
    candidate: str,
    char_profile: dict,
) -> str:
    background = char_profile.get("background") or ""
    arc = char_profile.get("arc") or ""
    prompt = (
        f"Character A: {char_a}\n"
        f"Character B: {char_b}\n"
        f"Existing relation: {existing}\n"
        f"Candidate relation: {candidate}\n"
        f"Character A background: {background}\n"
        f"Character A arc: {arc}"
    )
    result = await deduper.run(prompt)
    verdict = result.output.strip().lower()
    if verdict in ("merge", "keep_both", "unsure"):
        return verdict
    return "keep_both"


def make_scene_id(stem: str, chunk_idx: int, total_chunks: int) -> str:
    if total_chunks == 1:
        return f"scene-{stem}"
    return f"scene-{stem}-chunk-{chunk_idx:02d}"


@dataclass
class SceneOrchestrator:
    ctx: _PipelineContext
    resolver: EntityResolutionService
    analyzer: Any
    timeline_checker: Any
    narrative_checker: Any
    profiler: Any = None
    profiler_patch: Any = None
    beat_extractor: Any = None
    cleaner: Any = None
    relation_deduper: Any = None

    async def _clarify_relation_dedup(
        self,
        char_a_name: str,
        char_b_name: str,
        existing_rel: str,
        candidate_rel: str,
    ) -> str:
        queue = self.ctx.queue
        pending = self.ctx.pending_clarifications
        if not queue or pending is None:
            return "keep_both"

        clarification_id = str(uuid.uuid4())
        slot = ClarificationSlot()
        pending[clarification_id] = slot

        await _emit(
            queue,
            "clarification_needed",
            id=clarification_id,
            question=(
                f"Relation entre '{char_a_name}' et '{char_b_name}' : "
                f"'{existing_rel}' et '{candidate_rel}' décrivent-elles le même lien ?"
            ),
            entity_name=char_a_name,
            entity_context=f"Relation with {char_b_name}",
            existing_relation=existing_rel,
            candidate_relation=candidate_rel,
            options=["merge", "keep_both"],
        )

        try:
            await asyncio.wait_for(slot.event.wait(), timeout=CLARIFICATION_TIMEOUT)
        except TimeoutError:
            slot.answer = "keep_both"
        finally:
            pending.pop(clarification_id, None)

        return slot.answer if slot.answer in ("merge", "keep_both") else "keep_both"

    async def _is_relation_duplicate(
        self,
        new_rel: str,
        existing_rels: list[str],
        char_a_name: str,
        char_b_name: str,
        char_profile: dict,
    ) -> bool:
        if not existing_rels:
            return False
        best = max(existing_rels, key=lambda ex: fuzz.ratio(new_rel.lower(), ex.lower()))
        score = fuzz.ratio(new_rel.lower(), best.lower())
        if score >= 90:  # noqa: PLR2004
            return True  # évident textuellement, pas de LLM
        if self.relation_deduper:
            verdict = await _check_relation_semantic(
                self.relation_deduper, char_a_name, char_b_name,
                best, new_rel, char_profile,
            )
            if verdict == "unsure":
                verdict = await self._clarify_relation_dedup(
                    char_a_name, char_b_name, best, new_rel,
                )
            return verdict == "merge"
        return False

    async def _emit_status(self, status: ImportStatus) -> None:
        if self.ctx.queue:
            await _emit(
                self.ctx.queue,
                "status_change",
                status=status,
                current_scene=self.ctx.progress.current_scene,
                processed_scenes=self.ctx.progress.processed_scenes,
                total_scenes=self.ctx.progress.total_scenes,
            )

    async def process_scene(
        self,
        scene_file: Path,
        *,
        scene_id: str | None = None,
        chunk_text: str | None = None,
    ) -> tuple[list[dict], dict, list[tuple[Any, str, str | None, str | None]], str]:
        ctx = self.ctx
        if scene_id is None:
            scene_id = f"scene-{scene_file.stem}"
        ctx.progress.current_scene = scene_file.name
        ctx.progress.status = ImportStatus.ANALYZING
        await self._emit_status(ImportStatus.ANALYZING)

        raw_text = chunk_text if chunk_text is not None else await asyncio.to_thread(
            scene_file.read_text, encoding="utf-8"
        )
        if self.cleaner:
            try:
                scene_text = await clean_scene_text(self.cleaner, raw_text)
            except Exception:
                logger.exception("Scene cleaning failed for %s, using raw text", scene_file.name)
                scene_text = raw_text
        else:
            scene_text = raw_text
        analysis = await analyze_scene(self.analyzer, scene_text)

        if ctx.queue:
            await _emit(
                ctx.queue,
                "scene_analyzed",
                scene_id=scene_id,
                title=analysis.title,
                summary=analysis.summary,
                characters=[{"name": c.name, "role": c.role, "type": c.character_type} for c in analysis.characters],
                location=analysis.location.name,
                era=analysis.era,
                date=analysis.approximate_date,
                mood=analysis.mood,
            )

        ctx.progress.status = ImportStatus.RESOLVING
        await self._emit_status(ImportStatus.RESOLVING)
        scene_issues: list[dict] = []

        resolved_chars, resolved_groups = await self.resolver.resolve_characters(analysis, scene_text, scene_id, scene_issues)
        resolved_location = await self.resolver.resolve_location(analysis, scene_id, scene_issues)

        for rc, _, _, _ in resolved_chars:
            if rc.is_new:
                ctx.progress.new_characters.append(rc.name)
        if resolved_location.is_new:
            ctx.progress.new_locations.append(resolved_location.name)

        ctx.progress.status = ImportStatus.LOADING
        await self._emit_status(ImportStatus.LOADING)
        await load_scene(
            ctx.driver,
            ctx.collection,
            scene_id,
            scene_file.name,
            raw_text,  # full text for ChromaDB embedding
            analysis,
            resolved_chars,
            resolved_location,
            resolved_groups,
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
                for rc, role, _desc, _ctx in resolved_chars
            ],
            "groups": [
                {"name": rg.name, "id": rg.id, "role": role}
                for rg, role, _desc, _ctx in resolved_groups
            ],
            "location": {"name": resolved_location.name, "id": resolved_location.id},
        }

        ctx.progress.processed_scenes += 1
        return scene_issues, summary, resolved_chars, scene_text

    async def check_scene(self, scene_summary: dict) -> None:
        ctx = self.ctx
        ctx.progress.status = ImportStatus.CHECKING
        await self._emit_status(ImportStatus.CHECKING)

        if ctx.queue:
            await _emit(
                ctx.queue,
                "check_started",
                scene_id=scene_summary["scene_id"],
                scene_title=scene_summary.get("title"),
            )

        try:
            report = await check_scene_consistency(
                ctx.driver, ctx.collection, scene_summary, self.timeline_checker, self.narrative_checker
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

    async def _resolve_beat_participant(
        self, beat_id: str, name: str, role: str
    ) -> str | None:
        ctx = self.ctx
        match = fuzzy_match_entity(name, ctx.char_registry, ctx.char_aliases)
        if isinstance(match, AmbiguousMatch):
            char_id = match.best_id
        elif match.is_new:
            return None
        else:
            char_id = match.id
        await link_beat_character(ctx.driver, beat_id, char_id, role)
        return char_id

    async def _store_beat(self, beat_id: str, beat: NarrativeBeat, scene_id: str, i: int) -> None:
        ctx = self.ctx
        await create_narrative_beat(ctx.driver, beat_id, beat.action, scene_id)
        subject_id = await self._resolve_beat_participant(beat_id, beat.subject, "subject")
        object_id = await self._resolve_beat_participant(beat_id, beat.object, "object") if beat.object else None
        logger.debug(
            "  beat-%d: [%s] %s → %s → [%s] %s",
            i, beat.subject, subject_id or "?", beat.action, beat.object or "-", object_id or "-",
        )

    async def _extract_and_store_beats(
        self, scene_id: str, scene_text: str, active_names: list[str]
    ) -> list[NarrativeBeat]:
        try:
            beats = await extract_scene_beats(self.beat_extractor, scene_text, active_names)
            logger.debug("Scene %s — %d beats extracted", scene_id, len(beats))
            for i, beat in enumerate(beats):
                await self._store_beat(f"{scene_id}-beat-{i}", beat, scene_id, i)
            return beats
        except Exception:
            logger.exception("Beat extraction failed for scene: %s", scene_id)
            return []

    async def profile_scene_characters(  # noqa: PLR0912
        self,
        resolved_chars: list[tuple[Any, str, str | None, str | None]],
        scene_id: str,
        scene_text: str,
        scene_title: str,
    ) -> None:
        ctx = self.ctx
        ctx.progress.status = ImportStatus.PROFILING
        await self._emit_status(ImportStatus.PROFILING)

        known_names = list(ctx.char_registry.values())

        scene_beats: list[NarrativeBeat] = []
        if self.beat_extractor:
            active_names = [rc.name for rc, role, _, _ in resolved_chars if role != "mentioned"]
            if active_names:
                scene_beats = await self._extract_and_store_beats(scene_id, scene_text, active_names)

        for rc, role, desc, _ctx in resolved_chars:
            if role == "mentioned":
                continue

            char_id = rc.id
            char_name = rc.name

            try:
                existing_row = await get_character_profile(ctx.driver, char_id)
                existing_profile = existing_row if existing_row else {}
                has_profile = bool(existing_profile.get("background") or existing_profile.get("arc"))

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
                        self.profiler_patch or self.profiler, char_name, existing_profile,
                        scene_text, fragment, beats=char_beats,
                    )
                    await patch_character_profile_fields(ctx.driver, char_id, profile.model_dump())
                else:
                    profile = await profile_character(
                        self.profiler, char_name, [scene_text], [fragment], char_known_names,
                        beats=char_beats,
                    )
                    await update_character_profile(ctx.driver, char_id, profile.model_dump())

                stored_relations: list[dict[str, str]] = []
                for rel in profile.relations:
                    other_match = fuzzy_match_entity(rel.other_name, ctx.char_registry, ctx.char_aliases)
                    if isinstance(other_match, AmbiguousMatch):
                        other_id = other_match.best_id
                        other_name = other_match.best_name
                    else:
                        if other_match.is_new:
                            # Check if it's a known group → create MEMBER_OF
                            group_match = resolve_group_entity(rel.other_name, ctx.group_registry)
                            if not group_match.is_new:
                                await create_member_of(ctx.driver, char_id, group_match.id)
                            continue
                        other_id = other_match.id
                        other_name = other_match.name
                    if other_id != char_id:
                        a, b = sorted([char_id, other_id])
                        existing_rels = await get_relation_types_for_pair(ctx.driver, a, b)
                        is_duplicate = await self._is_relation_duplicate(
                            rel.relation, existing_rels,
                            char_name, other_name, existing_profile,
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
