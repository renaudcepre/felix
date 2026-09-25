"""Route d'ingestion de document (Étape 2, `plans/maintenance_profile.md` ;
streaming #import).

Une fiche procédure (PDF/txt/md) uploadée devient un graphe interrogeable :
sauvegarde dans un fichier TEMPORAIRE (le pipeline lit un chemin, cf.
`felix.ingest.document.read_pages`), ingestion via le même pipeline que le CLI
(`tools/ingest_doc.py`), streamée en SSE (mêmes events que la route de chat :
`phase`/`tool`/`alert`, plus `report`) — une ingestion prend 1 à 3 min, plus
question de laisser l'auteur devant un spinner muet tout du long. Le tour est
persisté en conversation comme un tour de chat (message utilisateur « Import :
<fichier> », cartes tool/alert, carte report finale) : même convention que
`felix.api.routes.atelier`, pour que l'import reste visible après reload.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, File, Form, UploadFile
from sse_starlette import EventSourceResponse, ServerSentEvent

from felix.api.deps import (  # noqa: TC001 — FastAPI résout ces annotations au runtime (DI)
    AtelierAgentsDep,
    ChronicleAgentsDep,
    Neo4jDriver,
    RelationAgentsDep,
)
from felix.atelier.agent import (
    ATELIER_CHOICES,
    DEFAULT_PROFILE,
    build_atelier_agent,
    build_chronicle_agent,
    build_relation_agent,
    resolve_profile,
)
from felix.atelier.pipeline import sse_text
from felix.core import link_produced, record_message
from felix.core.projects import DEFAULT_PROJECT
from felix.ingest.document import IngestReport, stream_ingest_document

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)

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
) -> EventSourceResponse:
    """Upload d'une fiche → flux SSE d'ingestion.

    Le nom de fichier d'origine est conservé (basename seul, anti-traversal) —
    il devient la prop `source` de l'entité `document` et sert à deviner
    l'extension (.pdf vs .txt/.md, cf. `read_pages`). L'écriture du fichier
    temporaire, l'ingestion ET sa suppression vivent TOUTES dans le générateur
    (pas avant) : une erreur à l'écriture devient un event `error` proprement
    formé plutôt qu'un 500 brut, et le nettoyage reste garanti (`finally`)
    même si le flux est interrompu en cours de route."""
    choice = ATELIER_CHOICES.get(profile, ATELIER_CHOICES[DEFAULT_PROFILE])
    # Profil RÉEL de ce projet (cf. atelier.py) : le seed pour un choix
    # évolutif tant qu'aucun changement n'a encore été validé, sinon le profil
    # stocké — les 3 agents extracteurs sont alors reconstruits pour lui (les
    # dicts pré-construits ne connaissent que le seed).
    resolved_profile = await resolve_profile(driver, choice, project=project)
    if choice.evolving:
        agent = build_atelier_agent(choice, resolved_profile)
        relation_agent = build_relation_agent(choice, resolved_profile)
        chronicle_agent = build_chronicle_agent(choice, resolved_profile)
    else:
        agent = agents[choice.key]
        relation_agent = relation_agents[choice.key]
        chronicle_agent = chronicle_agents[choice.key]
    safe_name = Path(file.filename or "document.txt").name or "document.txt"
    tmp_dir = Path(tempfile.mkdtemp(prefix="felix-ingest-"))
    tmp_path = tmp_dir / safe_name

    async def event_generator() -> AsyncGenerator[ServerSentEvent]:
        # Cartes du tour (tool/alert), retenues pour la persistance APRÈS le
        # flux — même convention que felix.api.routes.atelier (turn_cards).
        turn_cards: list[tuple[str, str]] = []
        report_json: str | None = None
        try:
            with tmp_path.open("wb") as out:
                shutil.copyfileobj(file.file, out)
            # Message utilisateur du tour d'import — persisté avant l'ingestion
            # (même loi que record_message côté chat : témoignage de la
            # demande, indépendant de la réussite de ce qui suit). Son id sert
            # plus bas à poser la provenance (#83).
            user_msg_id = await record_message(
                driver,
                "user",
                "text",
                f"Import : {safe_name}",
                project=project,
            )
            async for ev in stream_ingest_document(
                driver,
                tmp_path,
                profile=resolved_profile,
                agent=agent,
                relation_agent=relation_agent,
                chronicle_agent=chronicle_agent,
                project=project,
            ):
                yield ev
                if ev.event in ("tool", "alert"):
                    turn_cards.append((ev.event, sse_text(ev)))
                elif ev.event == "report":
                    report_json = ev.data

            # --- Persistance du tour en graphe, visible après reload ---
            for kind, data in turn_cards:
                await record_message(
                    driver,
                    "felix",
                    kind,
                    "",
                    payload=data,
                    project=project,
                )
            if report_json is not None:
                await record_message(
                    driver,
                    "felix",
                    "report",
                    "",
                    payload=report_json,
                    project=project,
                )
                # Provenance (#83) : MÊME helper que le chat
                # (felix.atelier.routes.atelier → link_produced sur deps.touched_ids) —
                # le message « Import : <fichier> » a produit les entités touchées
                # par l'ingestion. Scoping fort porté par link_produced lui-même.
                touched = set(IngestReport.model_validate_json(report_json).touched_ids)
                await link_produced(driver, user_msg_id, touched, project=project)
            yield ServerSentEvent(data="", event="done")
        except Exception as e:
            logger.exception("import de document échoué")
            yield ServerSentEvent(data=str(e), event="error")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return EventSourceResponse(event_generator())
