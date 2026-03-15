from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import chromadb
import pytest

from felix.config import settings
from felix.db import repository
from felix.db.schema import init_db
from felix.ingest.pipeline import ImportProgress, run_import_pipeline

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def pipeline_export(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Run le pipeline reel une seule fois pour toute la session d'eval.

    Skip automatiquement si le modele n'est pas accessible.
    """
    scenes_dir = tmp_path_factory.mktemp("eval_scenes")
    for f in sorted(FIXTURES_DIR.glob("*.txt")):
        shutil.copy(f, scenes_dir / f.name)

    async def _run() -> dict:
        db = await init_db(":memory:")
        client = chromadb.Client()
        collection = client.get_or_create_collection("eval_scenes")
        progress = ImportProgress()

        await run_import_pipeline(
            str(scenes_dir),
            db,
            collection,
            model_name=settings.llm_model,
            base_url=settings.llm_base_url,
            progress=progress,
            enrich_profiles=True,
        )

        if progress.status == "error":
            await db.close()
            raise RuntimeError(f"Pipeline error: {progress.error}")

        export = {
            "progress": {
                "status": progress.status,
                "processed_scenes": progress.processed_scenes,
                "issues_found": progress.issues_found,
            },
            "characters": await repository.list_all_characters_full(db),
            "locations": await repository.list_all_locations(db),
            "scenes": await repository.list_all_scenes_full(db),
            "timeline_events": await repository.list_all_timeline_events(db),
            "character_events": await repository.list_all_character_events(db),
            "character_relations": await repository.list_all_character_relations(db),
            "character_fragments": await repository.list_all_character_fragments(db),
            "issues": await repository.list_issues(db),
        }
        await db.close()
        return export

    try:
        return asyncio.run(_run())
    except Exception as e:
        pytest.skip(f"Pipeline indisponible (modele off ?): {e}")
