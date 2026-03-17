from __future__ import annotations

import asyncio
import json
import tempfile
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request, UploadFile
from felix.api.deps import BaseUrl, Collection, ModelName, Neo4jDriver
from pydantic import BaseModel
from sse_starlette import EventSourceResponse, ServerSentEvent

from felix.api.models import (
    ImportProgressResponse,
    Issue,
    IssueUpdate,
    SceneSummary,
)
from felix.graph.repository import get_issue_by_id, list_issues, list_scenes, update_issue_resolved
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


@router.post("/import", status_code=202)
async def start_import(
    request: Request,
    driver: Neo4jDriver,
    collection: Collection,
    model_name: ModelName,
    base_url: BaseUrl,
    files: list[UploadFile] = [],  # noqa: B006
    enrich: bool = True,
) -> ImportProgressResponse:
    progress: ImportProgress | None = getattr(
        request.app.state, "import_progress", None
    )
    if progress and progress.status not in (
        ImportStatus.DONE,
        ImportStatus.ERROR,
        ImportStatus.PENDING,
    ):
        raise HTTPException(status_code=409, detail="Import already in progress")

    txt_files = [f for f in files if f.filename and f.filename.lower().endswith(SCENE_FILE_EXTENSIONS)]
    if not txt_files:
        raise HTTPException(status_code=400, detail="Aucun fichier texte recu")

    tmp_dir = tempfile.mkdtemp(prefix="felix-import-")
    for upload in txt_files:
        content = await upload.read()
        dest = _tmp_path(tmp_dir) / upload.filename  # type: ignore[arg-type]
        dest.write_bytes(content)

    new_progress = ImportProgress()
    request.app.state.import_progress = new_progress

    request.app.state.import_task = asyncio.create_task(
        run_import_pipeline(
            tmp_dir, driver, collection, model_name, base_url, new_progress,
            enrich_profiles=enrich,
        )
    )

    return ImportProgressResponse(**new_progress.__dict__)


@router.post("/import/stream")
async def import_stream(
    request: Request,
    driver: Neo4jDriver,
    collection: Collection,
    model_name: ModelName,
    base_url: BaseUrl,
    files: list[UploadFile] = [],  # noqa: B006
    enrich: bool = True,
) -> EventSourceResponse:
    progress: ImportProgress | None = getattr(
        request.app.state, "import_progress", None
    )
    if progress and progress.status not in (
        ImportStatus.DONE,
        ImportStatus.ERROR,
        ImportStatus.PENDING,
    ):
        raise HTTPException(status_code=409, detail="Import already in progress")

    txt_files = [f for f in files if f.filename and f.filename.lower().endswith(SCENE_FILE_EXTENSIONS)]
    if not txt_files:
        raise HTTPException(status_code=400, detail="Aucun fichier texte recu")

    tmp_dir = tempfile.mkdtemp(prefix="felix-import-")
    for upload in txt_files:
        content = await upload.read()
        dest = _tmp_path(tmp_dir) / upload.filename  # type: ignore[arg-type]
        dest.write_bytes(content)

    new_progress = ImportProgress()
    request.app.state.import_progress = new_progress

    queue: EventQueue = asyncio.Queue()
    pending: dict[str, ClarificationSlot] = {}
    request.app.state.pending_clarifications = pending

    task = asyncio.create_task(
        run_import_pipeline(
            tmp_dir,
            driver,
            collection,
            model_name,
            base_url,
            new_progress,
            queue,
            pending,
            enrich_profiles=enrich,
        )
    )
    request.app.state.import_task = task

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
async def clarify(body: ClarifyRequest, request: Request) -> dict[str, str]:
    pending: dict[str, ClarificationSlot] | None = getattr(
        request.app.state, "pending_clarifications", None
    )
    if not pending or body.id not in pending:
        raise HTTPException(
            status_code=404, detail="Clarification not found or expired"
        )

    slot = pending[body.id]
    slot.answer = body.answer
    slot.event.set()
    return {"status": "ok"}


@router.get("/import/status")
async def get_import_status(request: Request) -> ImportProgressResponse:
    progress: ImportProgress | None = getattr(
        request.app.state, "import_progress", None
    )
    if not progress:
        return ImportProgressResponse(status=ImportStatus.PENDING)
    return ImportProgressResponse(**progress.__dict__)


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
