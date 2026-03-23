from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from felix.ingest.models import SceneAnalysis

from felix.graph.repositories.characters import add_character_alias
from felix.graph.repositories.locations import add_location_alias
from felix.ingest.resolver import (
    AmbiguousMatch,
    ResolvedEntity,
    fuzzy_match_entity,
    slugify,
)
from felix.ingest.utils import normalize

EventQueue = asyncio.Queue[dict[str, Any]]
EmitFn = Callable[..., Awaitable[None]] | None

CLARIFICATION_TIMEOUT = 30.0
_EXCERPT_MAX_LEN = 120


class ImportStatus(StrEnum):
    PENDING = "pending"
    SEGMENTING = "segmenting"
    ANALYZING = "analyzing"
    RESOLVING = "resolving"
    LOADING = "loading"
    CHECKING = "checking"
    PROFILING = "profiling"
    DONE = "done"
    ERROR = "error"


@dataclass
class ClarificationSlot:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    answer: str = ""


async def emit(queue: EventQueue, event: str, **data: Any) -> None:
    await queue.put({"event": event, **data})


def _find_excerpt(name: str, scene_text: str) -> str | None:
    """Return the first line of scene_text that contains the name (case-insensitive)."""
    for line in scene_text.splitlines():
        if name.lower() in line.lower() and line.strip():
            excerpt = line.strip()
            return excerpt[:_EXCERPT_MAX_LEN] + "…" if len(excerpt) > _EXCERPT_MAX_LEN else excerpt
    return None


async def handle_ambiguous_character(  # noqa: PLR0913
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
        await emit(
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
            await emit(queue, "entity_resolved", name=name, action="created")
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
        await emit(
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


def resolve_group_entity(name: str, group_registry: dict[str, str]) -> ResolvedEntity:
    """Résolution simplifiée pour groupes : exact match normalisé ou nouveau slug."""
    norm = normalize(name)
    for gid, gname in group_registry.items():
        if normalize(gname) == norm:
            return ResolvedEntity(id=gid, name=gname)
    new_id = slugify(name)
    return ResolvedEntity(id=new_id, name=name, is_new=True)


async def resolve_characters(  # noqa: PLR0913
    analysis: SceneAnalysis,
    scene_text: str,
    char_registry: dict[str, str],
    char_aliases: dict[str, list[str]],
    char_details: dict[str, dict],
    scene_id: str,
    issues: list[dict],
    driver: AsyncDriver,
    group_registry: dict[str, str],
    queue: EventQueue | None = None,
    pending_clarifications: dict[str, ClarificationSlot] | None = None,
) -> tuple[
    list[tuple[ResolvedEntity, str, str | None, str | None]],
    list[tuple[ResolvedEntity, str, str | None, str | None]],
]:
    resolved_chars: list[tuple[ResolvedEntity, str, str | None, str | None]] = []
    resolved_groups: list[tuple[ResolvedEntity, str, str | None, str | None]] = []

    for ec in analysis.characters:
        if ec.character_type == "group":
            resolved = resolve_group_entity(ec.name, group_registry)
            if resolved.is_new:
                group_registry[resolved.id] = resolved.name
            if queue:
                action = "created" if resolved.is_new else "linked"
                await emit(queue, "entity_resolved", name=ec.name, action=action)
            resolved_groups.append((resolved, ec.role, ec.description, ec.context))
            continue

        match = fuzzy_match_entity(ec.name, char_registry, char_aliases)
        if isinstance(match, AmbiguousMatch):
            context = ec.context or _find_excerpt(ec.name, scene_text)
            resolved = await handle_ambiguous_character(
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
                await emit(
                    queue,
                    "entity_resolved",
                    name=ec.name,
                    action=action,
                    linked_to=resolved.name if not resolved.is_new else None,
                    score=round(resolved.score, 2) if resolved.score is not None else None,
                )
        resolved_chars.append((resolved, ec.role, ec.description, ec.context))

    return resolved_chars, resolved_groups


async def resolve_location(  # noqa: PLR0913
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

            await emit(
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
                await emit(queue, "entity_resolved", name=analysis.location.name, action="created")
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
            await emit(
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
        await emit(
            queue,
            "entity_resolved",
            name=analysis.location.name,
            action=action,
            linked_to=match.name if not match.is_new else None,
        )
    return match


@dataclass
class EntityResolutionService:
    driver: AsyncDriver
    char_registry: dict[str, str]
    char_aliases: dict[str, list[str]]
    loc_registry: dict[str, str]
    loc_aliases: dict[str, list[str]]
    char_details: dict[str, dict]
    group_registry: dict[str, str]
    queue: EventQueue | None = None
    pending_clarifications: dict[str, ClarificationSlot] | None = None

    async def resolve_characters(
        self,
        analysis: SceneAnalysis,
        scene_text: str,
        scene_id: str,
        issues: list[dict],
    ) -> tuple[
        list[tuple[ResolvedEntity, str, str | None, str | None]],
        list[tuple[ResolvedEntity, str, str | None, str | None]],
    ]:
        return await resolve_characters(
            analysis,
            scene_text,
            self.char_registry,
            self.char_aliases,
            self.char_details,
            scene_id,
            issues,
            self.driver,
            self.group_registry,
            self.queue,
            self.pending_clarifications,
        )

    async def resolve_location(
        self,
        analysis: SceneAnalysis,
        scene_id: str,
        issues: list[dict],
    ) -> ResolvedEntity:
        return await resolve_location(
            analysis,
            self.loc_registry,
            self.loc_aliases,
            self.driver,
            scene_id,
            issues,
            self.queue,
            self.pending_clarifications,
        )
