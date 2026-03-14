from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile

from felix.api.models import (
    ImportProgressResponse,
    Issue,
    IssueUpdate,
    SceneSummary,
)
from felix.db.queries import list_issues, list_scenes, update_issue_resolved
from felix.ingest.pipeline import ImportProgress, ImportStatus, run_import_pipeline

router = APIRouter(prefix="/api", tags=["ingest"])


@router.post("/import", status_code=202)
async def start_import(
    request: Request, files: list[UploadFile] = [],  # noqa: B006
) -> ImportProgressResponse:
    progress: ImportProgress | None = getattr(request.app.state, "import_progress", None)
    if progress and progress.status not in (ImportStatus.DONE, ImportStatus.ERROR, ImportStatus.PENDING):
        raise HTTPException(status_code=409, detail="Import already in progress")

    txt_files = [f for f in files if f.filename and f.filename.endswith(".txt")]
    if not txt_files:
        raise HTTPException(status_code=400, detail="Aucun fichier .txt recu")

    # Write uploaded files to a temp directory
    tmp_dir = tempfile.mkdtemp(prefix="felix-import-")
    for upload in txt_files:
        content = await upload.read()
        dest = Path(tmp_dir) / upload.filename  # type: ignore[arg-type]
        dest.write_bytes(content)

    new_progress = ImportProgress()
    request.app.state.import_progress = new_progress

    db = request.app.state.db
    collection = request.app.state.deps.chroma_collection
    model_name = request.app.state.model_name
    base_url = request.app.state.base_url

    request.app.state.import_task = asyncio.create_task(
        run_import_pipeline(
            tmp_dir, db, collection, model_name, base_url, new_progress
        )
    )

    return ImportProgressResponse(**new_progress.__dict__)


@router.get("/import/status")
async def get_import_status(request: Request) -> ImportProgressResponse:
    progress: ImportProgress | None = getattr(request.app.state, "import_progress", None)
    if not progress:
        return ImportProgressResponse(status=ImportStatus.PENDING)
    return ImportProgressResponse(**progress.__dict__)


@router.get("/issues")
async def get_issues(
    request: Request,
    type: str | None = None,
    severity: str | None = None,
    resolved: bool | None = None,
) -> list[Issue]:
    db = request.app.state.db
    rows = await list_issues(db, type=type, severity=severity, resolved=resolved)
    return [Issue(**row) for row in rows]


@router.patch("/issues/{issue_id}")
async def patch_issue(issue_id: str, body: IssueUpdate, request: Request) -> Issue:
    db = request.app.state.db
    ok = await update_issue_resolved(db, issue_id, body.resolved)
    if not ok:
        raise HTTPException(status_code=404, detail="Issue not found")
    rows = await list_issues(db)
    row = next((r for r in rows if r["id"] == issue_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Issue not found")
    return Issue(**row)


@router.get("/scenes")
async def get_scenes(request: Request) -> list[SceneSummary]:
    db = request.app.state.db
    rows = await list_scenes(db)
    return [SceneSummary(**row) for row in rows]
