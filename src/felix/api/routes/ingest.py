"""Route d'ingestion de document (Étape 2, `plans/maintenance_profile.md`).

Une fiche procédure (PDF/txt/md) uploadée devient un graphe interrogeable :
sauvegarde dans un fichier TEMPORAIRE (le pipeline lit un chemin, cf.
`felix.ingest.document.read_pages`), ingestion via le même pipeline que le CLI
(`tools/ingest_doc.py`), résumé retourné (`IngestReport`).
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile

from felix.api.deps import (  # noqa: TC001 — FastAPI résout ces annotations au runtime (DI)
    AtelierAgentsDep,
    ChronicleAgentsDep,
    Neo4jDriver,
    RelationAgentsDep,
)
from felix.atelier.agent import ATELIER_CHOICES, DEFAULT_PROFILE
from felix.core.projects import DEFAULT_PROJECT
from felix.ingest.document import IngestReport, ingest_document

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


@router.post("/document")
async def post_ingest_document(  # noqa: PLR0913 — 3 deps d'agents + driver + 3 champs de formulaire
    driver: Neo4jDriver,
    agents: AtelierAgentsDep,
    relation_agents: RelationAgentsDep,
    chronicle_agents: ChronicleAgentsDep,
    file: UploadFile = File(...),  # noqa: B008 — pattern FastAPI standard
    profile: str = Form(default="maintenance"),
    project: str = Form(default=DEFAULT_PROJECT),
) -> IngestReport:
    """Upload d'une fiche → ingestion en base, résumé retourné.

    Le nom de fichier d'origine est conservé (basename seul, anti-traversal) —
    il devient la prop `source` de l'entité `document` et sert à deviner
    l'extension (.pdf vs .txt/.md, cf. `read_pages`). Le fichier temporaire est
    supprimé après l'ingestion, réussie ou non."""
    choice = ATELIER_CHOICES.get(profile, ATELIER_CHOICES[DEFAULT_PROFILE])
    safe_name = Path(file.filename or "document.txt").name or "document.txt"
    tmp_dir = Path(tempfile.mkdtemp(prefix="felix-ingest-"))
    tmp_path = tmp_dir / safe_name
    try:
        with tmp_path.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        return await ingest_document(
            driver, tmp_path,
            profile=choice.profile,
            agent=agents[choice.key],
            relation_agent=relation_agents[choice.key],
            chronicle_agent=chronicle_agents[choice.key],
            project=project,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
