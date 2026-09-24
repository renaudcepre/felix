"""CLI d'ingestion de document (Étape 2, `plans/maintenance_profile.md`).

Ingère une fiche (PDF/txt/md) dans le graphe, hors API — utile en dev et pour
vérifier une fiche avant de la brancher sur le front. APPELLE LE LLM (3 passes
par bloc : entités, relieur, chroniqueur si le domaine en tient un).

Usage : uv run python tools/ingest_doc.py <path> [--profile maintenance] [--project NAME]
"""
# ruff: noqa: T201 — CLI, le print EST la sortie
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from felix.atelier.agent import (
    ATELIER_CHOICES,
    DEFAULT_PROFILE,
    build_atelier_agent,
    build_chronicle_agent,
    build_relation_agent,
)
from felix.core.projects import DEFAULT_PROJECT
from felix.graph.driver import get_driver, setup_constraints
from felix.ingest.document import ingest_document


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Fichier à ingérer (PDF, .txt, .md)")
    parser.add_argument(
        "--profile", default="maintenance", choices=sorted(ATELIER_CHOICES),
        help="Profil de domaine (défaut : maintenance)",
    )
    parser.add_argument(
        "--project", default=DEFAULT_PROJECT, help="Projet/histoire cible (défaut : defaut)",
    )
    return parser.parse_args()


async def main() -> int:
    args = _parse_args()
    if not args.path.exists():
        print(f"✗ fichier introuvable : {args.path}")
        return 1

    choice = ATELIER_CHOICES.get(args.profile, ATELIER_CHOICES[DEFAULT_PROFILE])
    driver = get_driver()
    try:
        await setup_constraints(driver)
        report = await ingest_document(
            driver, args.path,
            profile=choice.profile,
            agent=build_atelier_agent(choice),
            relation_agent=build_relation_agent(choice),
            chronicle_agent=build_chronicle_agent(choice),
            project=args.project,
        )
    finally:
        await driver.close()

    print(f"« {report.title} » (id: {report.document_id}) — projet {args.project!r}")
    print(f"  blocs traités  : {report.chunks}")
    print(f"  entités touchées : {report.entities_touched}")
    print(f"  relations créées : {report.relations}")
    print(f"  tokens (req/rép/total) : "
          f"{report.request_tokens}/{report.response_tokens}/{report.total_tokens}")
    if report.alerts:
        print(f"  alertes de cohérence ({len(report.alerts)}) :")
        for alert in report.alerts:
            print(f"    - {alert}")
    if report.errors:
        print(f"  blocs en échec ({len(report.errors)}) :")
        for err in report.errors:
            print(f"    - {err}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
