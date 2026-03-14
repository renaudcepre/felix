from __future__ import annotations

import contextlib
import json
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite
    import chromadb

    from felix.ingest.models import SceneAnalysis

from felix.db.queries import (
    create_issue,
    delete_issues_for_scenes,
)
from felix.ingest.analyzer import analyze_scene, create_analyzer_agent
from felix.ingest.checker import check_consistency, create_checker_agent
from felix.ingest.loader import load_scene
from felix.ingest.resolver import (
    AmbiguousMatch,
    ResolvedEntity,
    fuzzy_match_entity,
)


class ImportStatus(StrEnum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    RESOLVING = "resolving"
    LOADING = "loading"
    CHECKING = "checking"
    DONE = "done"
    ERROR = "error"


@dataclass
class ImportProgress:
    status: ImportStatus = ImportStatus.PENDING
    total_scenes: int = 0
    processed_scenes: int = 0
    current_scene: str = ""
    issues_found: int = 0
    error: str = ""
    new_characters: list[str] = field(default_factory=list)
    new_locations: list[str] = field(default_factory=list)


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
) -> tuple[dict[str, str], dict[str, list[str]], dict[str, str]]:
    cursor = await db.execute("SELECT id, name, aliases FROM characters")
    chars = [dict(row) for row in await cursor.fetchall()]

    cursor = await db.execute("SELECT id, name FROM locations")
    locs = [dict(row) for row in await cursor.fetchall()]

    return _build_registry(chars, locs)


def _resolve_characters(
    analysis: SceneAnalysis,
    char_registry: dict[str, str],
    char_aliases: dict[str, list[str]],
    scene_id: str,
    issues: list[dict],
) -> list[tuple[ResolvedEntity, str]]:
    resolved_chars: list[tuple[ResolvedEntity, str]] = []
    for ec in analysis.characters:
        match = fuzzy_match_entity(ec.name, char_registry, char_aliases)
        if isinstance(match, AmbiguousMatch):
            issues.append({
                "id": str(uuid.uuid4()),
                "type": "duplicate_suspect",
                "severity": "warning",
                "scene_id": scene_id,
                "entity_id": match.best_id,
                "description": (
                    f"Personnage '{ec.name}' ressemble a '{match.best_name}' "
                    f"(score {match.score:.2f}). Lien automatique effectue."
                ),
                "suggestion": f"Verifier si '{ec.name}' est bien '{match.best_name}'.",
            })
            resolved = ResolvedEntity(id=match.best_id, name=match.best_name)
        else:
            resolved = match
            if resolved.is_new:
                char_registry[resolved.id] = resolved.name
        resolved_chars.append((resolved, ec.role))
    return resolved_chars


def _resolve_location(
    analysis: SceneAnalysis,
    loc_registry: dict[str, str],
    scene_id: str,
    issues: list[dict],
) -> ResolvedEntity:
    match = fuzzy_match_entity(analysis.location.name, loc_registry)
    if isinstance(match, AmbiguousMatch):
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
    return match


async def run_import_pipeline(  # noqa: PLR0913
    scenes_dir: str,
    db: aiosqlite.Connection,
    collection: chromadb.Collection,
    model_name: str | None,
    base_url: str | None,
    progress: ImportProgress,
) -> None:
    try:
        # 1. List .txt files
        scene_files = sorted(Path(scenes_dir).glob("*.txt"))  # noqa: ASYNC240
        if not scene_files:
            progress.error = f"Aucun fichier .txt dans {scenes_dir}"
            progress.status = ImportStatus.ERROR
            return

        progress.total_scenes = len(scene_files)

        # 2. Load registries from DB
        char_registry, char_aliases, loc_registry = await _load_registries(db)

        # 3. Delete old issues for scenes being re-imported
        scene_ids = [f"scene-{f.stem}" for f in scene_files]
        await delete_issues_for_scenes(db, scene_ids)

        # 4. Create analyzer agent
        analyzer = create_analyzer_agent(model_name, base_url)

        all_issues: list[dict] = []
        scenes_summary: list[dict] = []

        # 5. Process each scene
        for scene_file in scene_files:
            scene_id = f"scene-{scene_file.stem}"
            progress.current_scene = scene_file.name
            progress.status = ImportStatus.ANALYZING

            scene_text = scene_file.read_text(encoding="utf-8")

            # Analyze
            analysis = await analyze_scene(analyzer, scene_text)

            # Resolve
            progress.status = ImportStatus.RESOLVING
            scene_issues: list[dict] = []

            resolved_chars = _resolve_characters(
                analysis, char_registry, char_aliases, scene_id, scene_issues
            )
            resolved_location = _resolve_location(
                analysis, loc_registry, scene_id, scene_issues
            )

            # Track new entities
            for rc, _ in resolved_chars:
                if rc.is_new:
                    progress.new_characters.append(rc.name)
            if resolved_location.is_new:
                progress.new_locations.append(resolved_location.name)

            # Load
            progress.status = ImportStatus.LOADING
            await load_scene(
                db, collection, scene_id, scene_file.name, scene_text,
                analysis, resolved_chars, resolved_location,
            )

            all_issues.extend(scene_issues)
            scenes_summary.append({
                "scene_id": scene_id,
                "title": analysis.title,
                "summary": analysis.summary,
                "era": analysis.era,
                "date": analysis.approximate_date,
                "characters": [
                    {"name": rc.name, "id": rc.id, "role": role}
                    for rc, role in resolved_chars
                ],
                "location": {
                    "name": resolved_location.name,
                    "id": resolved_location.id,
                },
            })

            progress.processed_scenes += 1

        # 6. Cross-scene consistency check
        progress.status = ImportStatus.CHECKING
        progress.current_scene = ""
        checker = create_checker_agent(model_name, base_url)
        report = await check_consistency(checker, scenes_summary)
        for ci in report.issues:
            all_issues.append({
                "id": str(uuid.uuid4()),
                "type": ci.type,
                "severity": ci.severity,
                "scene_id": ci.scene_id,
                "entity_id": ci.entity_id,
                "description": ci.description,
                "suggestion": ci.suggestion,
            })

        # 7. Insert all issues
        for issue in all_issues:
            await create_issue(db, issue)

        progress.issues_found = len(all_issues)
        progress.status = ImportStatus.DONE

    except Exception as e:
        progress.error = str(e)
        progress.status = ImportStatus.ERROR
