"""CLI du schéma ÉMERGENT (Étape 7, `plans/maintenance_profile.md`).

Sous-commandes :
- ``profile``      : affiche le profil RÉEL du projet (stocké, sinon le seed).
- ``proposals``     : liste les propositions déterministes du détecteur (aucun
  appel LLM) — chacune avec son rapport en PREVIEW.
- ``apply --json '<change>'`` : applique UN changement (migre le passé, fait
  évoluer le profil, sauvegarde).
- ``accept-all``    : l'HUMAIN SIMULÉ du POC — applique TOUTES les propositions
  courantes, d'affilée.

Aucune commande n'appelle le LLM (le détecteur est déterministe).

Usage :
  uv run python tools/schema.py profile --project e2e-emergent
  uv run python tools/schema.py proposals --project e2e-emergent
  uv run python tools/schema.py apply --project e2e-emergent \\
      --json '{"kind": "promote_verbs", "verbe_slugs": ["regle"], "rel_type": "CONTROLS"}'
  uv run python tools/schema.py accept-all --project e2e-emergent
"""
# ruff: noqa: T201 — CLI, le print EST la sortie
from __future__ import annotations

import argparse
import asyncio
import json
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from felix.atelier.agent import ATELIER_CHOICES, resolve_profile
from felix.core.profile_evolution import evolve_profile
from felix.core.profile_store import profile_to_dict, save_project_profile
from felix.core.projects import DEFAULT_PROJECT
from felix.core.schema_changes import SchemaChange, apply_schema_change
from felix.core.schema_detector import detect_proposals
from felix.graph.driver import get_driver, setup_constraints

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from felix.core.profile import Profile
    from felix.core.schema_detector import Proposal

_CHANGE_ADAPTER: TypeAdapter[SchemaChange] = TypeAdapter(SchemaChange)


def _parse_args() -> argparse.Namespace:
    # --project est déclaré sur CHAQUE sous-commande (jamais sur le parser
    # racine) : avec des sous-parsers, un flag du parent PLACÉ AVANT la
    # sous-commande est silencieusement écrasé par le défaut du sous-parser
    # (argparse construit une Namespace SÉPARÉE pour la sous-commande puis
    # l'applique par-dessus) — piège vérifié, d'où ce choix : ``--project``
    # ne s'écrit QU'APRÈS la sous-commande (cf. docstring du module).
    project_parent = argparse.ArgumentParser(add_help=False)
    project_parent.add_argument(
        "--project", default=DEFAULT_PROJECT, help="Projet cible (défaut : defaut)",
    )

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("profile", help="Affiche le profil réel du projet", parents=[project_parent])
    p_proposals = sub.add_parser(
        "proposals", help="Liste les propositions du détecteur", parents=[project_parent],
    )
    p_proposals.add_argument("--min-count", type=int, default=2)
    p_apply = sub.add_parser(
        "apply", help="Applique un changement (migre + évolue + sauve)",
        parents=[project_parent],
    )
    p_apply.add_argument("--json", required=True, dest="change_json",
                          help="Le SchemaChange en JSON (PromoteVerbs ou MergeTypes)")
    p_accept = sub.add_parser(
        "accept-all", help="Accepte toutes les propositions courantes",
        parents=[project_parent],
    )
    p_accept.add_argument("--min-count", type=int, default=2)
    return parser.parse_args()


async def _current_profile(driver: AsyncDriver, project: str) -> Profile:
    choice = ATELIER_CHOICES["emergent"]
    profile = await resolve_profile(driver, choice, project=project)
    assert profile is not None  # le choix "emergent" a toujours un profil (le seed au pire)
    return profile


def _print_proposal(proposal: Proposal) -> None:
    print(f"  - {proposal.change.model_dump_json()}")
    if proposal.report.samples:
        print(f"    échantillons : {proposal.report.samples}")
    if proposal.report.observed_pairs:
        print(f"    paires observées : {proposal.report.observed_pairs}")


async def cmd_profile(driver: AsyncDriver, project: str) -> int:
    profile = await _current_profile(driver, project)
    print(json.dumps(profile_to_dict(profile), ensure_ascii=False, indent=2))
    return 0


async def cmd_proposals(driver: AsyncDriver, project: str, min_count: int) -> int:
    profile = await _current_profile(driver, project)
    proposals = await detect_proposals(
        driver, project=project, profile=profile, min_count=min_count
    )
    if not proposals:
        print("Aucune proposition.")
        return 0
    print(f"{len(proposals)} proposition(s) :")
    for proposal in proposals:
        _print_proposal(proposal)
    return 0


async def cmd_apply(driver: AsyncDriver, project: str, change_json: str) -> int:
    change = _CHANGE_ADAPTER.validate_json(change_json)
    report = await apply_schema_change(driver, change, project=project, preview=False)
    profile = await _current_profile(driver, project)
    new_profile = evolve_profile(profile, change, report)
    version = await save_project_profile(driver, new_profile, project=project)
    print(f"Changement appliqué (profil version {version}) : {report.samples}")
    return 0


async def cmd_accept_all(driver: AsyncDriver, project: str, min_count: int) -> int:
    """L'humain simulé du POC : applique TOUTES les propositions courantes, une
    par une, en ré-évoluant le profil à chaque pas."""
    profile = await _current_profile(driver, project)
    proposals = await detect_proposals(
        driver, project=project, profile=profile, min_count=min_count
    )
    if not proposals:
        print("Aucune proposition à accepter.")
        return 0
    for proposal in proposals:
        report = await apply_schema_change(
            driver, proposal.change, project=project, preview=False
        )
        profile = evolve_profile(profile, proposal.change, report)
        print(f"  ✓ {proposal.change.model_dump_json()}")
    version = await save_project_profile(driver, profile, project=project)
    print(f"{len(proposals)} changement(s) appliqué(s), profil version {version}.")
    return 0


async def main() -> int:
    args = _parse_args()
    driver = get_driver()
    try:
        await setup_constraints(driver)
        if args.command == "profile":
            return await cmd_profile(driver, args.project)
        if args.command == "proposals":
            return await cmd_proposals(driver, args.project, args.min_count)
        if args.command == "apply":
            return await cmd_apply(driver, args.project, args.change_json)
        return await cmd_accept_all(driver, args.project, args.min_count)
    finally:
        await driver.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
