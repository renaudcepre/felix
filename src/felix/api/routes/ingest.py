from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel
from sse_starlette import EventSourceResponse, ServerSentEvent

from felix.api.deps import BaseUrl, Collection, ImportStateDep, ModelName, Neo4jDriver

logger = logging.getLogger(__name__)


def _log_task_exception(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.exception("Unhandled exception in background import task", exc_info=exc)

from felix.api.models import (
    ImportProgressResponse,
    Issue,
    IssueUpdate,
    SceneSummary,
)
from felix.graph.repositories.issues import get_issue_by_id, list_issues, update_issue_resolved
from felix.graph.repositories.scenes import list_scenes
from felix.config import SCENE_FILE_EXTENSIONS
from felix.ingest.pipeline import (
    ClarificationSlot,
    EventQueue,
    ImportProgress,
    ImportStatus,
    run_import_pipeline,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

router = APIRouter(prefix="/api", tags=["ingest"])


class ClarifyRequest(BaseModel):
    id: str
    answer: str  # "link" or "new"


_TERMINAL_STATUSES = (ImportStatus.DONE, ImportStatus.ERROR, ImportStatus.PENDING)


@router.post("/import", status_code=202)
async def start_import(
    import_state: ImportStateDep,
    driver: Neo4jDriver,
    collection: Collection,
    model_name: ModelName,
    base_url: BaseUrl,
    files: list[UploadFile] = [],  # noqa: B006
    enrich: bool = True,
) -> ImportProgressResponse:
    txt_files = [f for f in files if f.filename and f.filename.lower().endswith(SCENE_FILE_EXTENSIONS)]
    if not txt_files:
        raise HTTPException(status_code=400, detail="Aucun fichier texte recu")

    contents = [(upload.filename, await upload.read()) for upload in txt_files]

    async with import_state.lock:
        if import_state.progress and import_state.progress.status not in _TERMINAL_STATUSES:
            raise HTTPException(status_code=409, detail="Import already in progress")

        tmp_dir = tempfile.mkdtemp(prefix="felix-import-")
        for filename, content in contents:
            (_tmp_path(tmp_dir) / filename).write_bytes(content)  # type: ignore[operator]

        new_progress = ImportProgress()
        import_state.progress = new_progress
        import_state.task = asyncio.create_task(
            run_import_pipeline(
                tmp_dir, driver, collection, model_name, base_url, new_progress,
                enrich_profiles=enrich,
            )
        )
        import_state.task.add_done_callback(_log_task_exception)

    return ImportProgressResponse.model_validate(new_progress, from_attributes=True)


@router.post("/import/stream")
async def import_stream(
    import_state: ImportStateDep,
    driver: Neo4jDriver,
    collection: Collection,
    model_name: ModelName,
    base_url: BaseUrl,
    files: list[UploadFile] = [],  # noqa: B006
    enrich: bool = True,
) -> EventSourceResponse:
    txt_files = [f for f in files if f.filename and f.filename.lower().endswith(SCENE_FILE_EXTENSIONS)]
    if not txt_files:
        raise HTTPException(status_code=400, detail="Aucun fichier texte recu")

    contents = [(upload.filename, await upload.read()) for upload in txt_files]

    async with import_state.lock:
        if import_state.progress and import_state.progress.status not in _TERMINAL_STATUSES:
            raise HTTPException(status_code=409, detail="Import already in progress")

        tmp_dir = tempfile.mkdtemp(prefix="felix-import-")
        for filename, content in contents:
            (_tmp_path(tmp_dir) / filename).write_bytes(content)  # type: ignore[operator]

        new_progress = ImportProgress()
        import_state.progress = new_progress

        queue: EventQueue = asyncio.Queue()
        pending: dict[str, ClarificationSlot] = {}
        import_state.pending_clarifications = pending

        task = asyncio.create_task(
            run_import_pipeline(
                tmp_dir, driver, collection, model_name, base_url, new_progress,
                queue, pending, enrich_profiles=enrich,
            )
        )
        task.add_done_callback(_log_task_exception)
        import_state.task = task

    async def event_generator() -> AsyncGenerator[ServerSentEvent]:
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                except TimeoutError:
                    if task.done():
                        while not queue.empty():
                            event = queue.get_nowait()
                            yield ServerSentEvent(
                                data=json.dumps(event),
                                event=event["event"],
                            )
                        break
                    continue

                yield ServerSentEvent(
                    data=json.dumps(event),
                    event=event["event"],
                )

                if event["event"] in ("done", "error"):
                    break
        except asyncio.CancelledError:
            pass

    return EventSourceResponse(
        event_generator(),
        headers={"X-Accel-Buffering": "no"},
    )


@router.post("/import/clarify")
async def clarify(body: ClarifyRequest, import_state: ImportStateDep) -> dict[str, str]:
    pending = import_state.pending_clarifications
    if not pending or body.id not in pending:
        raise HTTPException(
            status_code=404, detail="Clarification not found or expired"
        )

    slot = pending[body.id]
    slot.answer = body.answer
    slot.event.set()
    return {"status": "ok"}


@router.get("/import/status")
async def get_import_status(import_state: ImportStateDep) -> ImportProgressResponse:
    if not import_state.progress:
        return ImportProgressResponse(status=ImportStatus.PENDING)
    return ImportProgressResponse.model_validate(import_state.progress, from_attributes=True)


@router.get("/issues")
async def get_issues(
    driver: Neo4jDriver,
    type: str | None = None,
    severity: str | None = None,
    resolved: bool | None = None,
) -> list[Issue]:
    rows = await list_issues(driver, type=type, severity=severity, resolved=resolved)
    return [Issue(**row) for row in rows]


@router.patch("/issues/{issue_id}")
async def patch_issue(issue_id: str, body: IssueUpdate, driver: Neo4jDriver) -> Issue:
    ok = await update_issue_resolved(driver, issue_id, body.resolved)
    if not ok:
        raise HTTPException(status_code=404, detail="Issue not found")
    row = await get_issue_by_id(driver, issue_id)
    if not row:
        raise HTTPException(status_code=404, detail="Issue not found")
    return Issue(**row)


@router.get("/scenes")
async def get_scenes(driver: Neo4jDriver) -> list[SceneSummary]:
    rows = await list_scenes(driver)
    return [SceneSummary(**row) for row in rows]


def _tmp_path(tmp_dir: str) -> Path:
    from pathlib import Path

    return Path(tmp_dir)
