"""E2E de la boucle profil ÉMERGENT (Étape 9, `plans/maintenance_profile.md`) —
APPELLE LE LLM.

Scénario : projet ``e2e-emergent``, noyau NU au départ (EMERGENT_SEED_PROFILE,
zéro type, zéro vocabulaire de relation). Ingestion de la fiche 1 (SX-40,
réglage) → le détecteur DÉTERMINISTE (aucun LLM) propose des changements de
schéma → l'humain SIMULÉ accepte tout (le POC : pas encore de file de
validation front) → la migration du passé + l'évolution du profil sont
vérifiées → ingestion de la fiche 2 (SX-40, maintenance) avec le profil
ÉVOLUÉ → mesure la RÉUTILISATION des types promus (ratio typé / (typé + LIE_A))
comparée à la fiche 1.

Scopé à SON projet : seules les :GenEntity/:ProjectProfile/relations de
``e2e-emergent`` sont wipées au démarrage — les autres histoires de la base ne
sont jamais touchées (garantie #60, cf. felix.core.projects).

À lancer à la demande (2 fiches x ~3 blocs, quelques dizaines d'appels LLM) :
``just e2e-emergent``. Sort en code 1 si un invariant casse.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from felix.atelier.agent import (
    ATELIER_CHOICES,
    build_atelier_agent,
    build_chronicle_agent,
    build_relation_agent,
    resolve_profile,
)
from felix.core.graph import NARRATIVE_REL, all_relations
from felix.core.profile_evolution import evolve_profile
from felix.core.profile_store import load_project_profile, save_project_profile
from felix.core.schema_changes import PromoteVerbs, apply_schema_change
from felix.core.schema_detector import detect_proposals
from felix.graph.driver import get_driver, setup_constraints
from felix.ingest.document import ingest_document

if TYPE_CHECKING:
    from felix.core.profile import Profile
    from felix.core.schema_detector import Proposal
    from felix.ingest.document import IngestReport

PROJECT = "e2e-emergent"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
FICHE_1 = FIXTURES / "sx40_fiche.txt"
FICHE_2 = FIXTURES / "sx40_maintenance.txt"

CHOICE = ATELIER_CHOICES["emergent"]
MIN_COUNT = 2


async def _wipe_project(driver) -> None:
    """Wipe SCOPÉ à ``PROJECT`` — les autres histoires de la base ne sont
    jamais touchées (cf. #60, garantie structurelle du scoping projet)."""
    async with driver.session() as session:
        await session.run(
            "MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=PROJECT,
        )
        await session.run(
            "MATCH (n:ProjectProfile {project: $p}) DETACH DELETE n", p=PROJECT,
        )


def rel_counts(relations: list[dict]) -> tuple[int, int]:
    """(nombre de LIE_A, nombre de typées hors DESCRIBED_IN) — pure, testable
    sans Neo4j sur une liste de lignes ``all_relations``."""
    narrative = sum(1 for r in relations if r["rel_type"] == NARRATIVE_REL)
    typed = sum(
        1 for r in relations if r["rel_type"] not in (NARRATIVE_REL, "DESCRIBED_IN")
    )
    return narrative, typed


def reuse_ratio(narrative: int, typed: int) -> float:
    """typé / (typé + LIE_A) — 0 si aucune relation."""
    total = narrative + typed
    return typed / total if total else 0.0


async def _ingest(driver, path: Path, profile: Profile) -> IngestReport:
    agent = build_atelier_agent(CHOICE, profile)
    relation_agent = build_relation_agent(CHOICE, profile)
    chronicle_agent = build_chronicle_agent(CHOICE, profile)
    return await ingest_document(
        driver, path, profile=profile, agent=agent, relation_agent=relation_agent,
        chronicle_agent=chronicle_agent, project=PROJECT,
    )


def _print_proposal(proposal: Proposal) -> None:
    print(f"  - {proposal.change.model_dump_json()}")
    print(f"    échantillons : {proposal.report.samples}")
    print(f"    paires observées : {proposal.report.observed_pairs}")


async def main() -> int:  # noqa: PLR0915 — script e2e narratif, pas une lib
    driver = get_driver()
    checks: list[tuple[str, bool, str]] = []
    try:
        await setup_constraints(driver)
        await _wipe_project(driver)

        # ── Fiche 1 : profil = noyau nu (seed) ──
        profile = await resolve_profile(driver, CHOICE, project=PROJECT)
        assert profile is not None
        report1 = await _ingest(driver, FICHE_1, profile)
        relations1 = await all_relations(driver, project=PROJECT)
        lie_a_1, typed_1 = rel_counts(relations1)
        ratio_1 = reuse_ratio(lie_a_1, typed_1)
        print(
            f"Fiche 1 : {report1.entities_touched} entités, {lie_a_1} LIE_A, "
            f"{typed_1} typées, {report1.total_tokens} tokens"
        )

        # ── Détection déterministe (aucun LLM) ──
        proposals = await detect_proposals(
            driver, project=PROJECT, profile=profile, min_count=MIN_COUNT
        )
        print(f"\n{len(proposals)} proposition(s) :")
        for proposal in proposals:
            _print_proposal(proposal)

        # ── Validation « humain simulé » : accept-all ──
        promoted_slugs: set[str] = set()
        promoted_rel_types: set[str] = set()
        for proposal in proposals:
            real_report = await apply_schema_change(
                driver, proposal.change, project=PROJECT, preview=False
            )
            profile = evolve_profile(profile, proposal.change, real_report)
            if isinstance(proposal.change, PromoteVerbs):
                promoted_slugs.update(proposal.change.verbe_slugs)
                promoted_rel_types.add(proposal.change.rel_type)
        stored_version = None
        if proposals:
            stored_version = await save_project_profile(driver, profile, project=PROJECT)

        # ── Invariants post-validation ──
        relations_after_accept = await all_relations(driver, project=PROJECT)
        remaining_promoted_lie_a = [
            r for r in relations_after_accept
            if r["rel_type"] == NARRATIVE_REL
            and r["props"].get("verbe_slug") in promoted_slugs
        ]
        stored_profile = await load_project_profile(driver, project=PROJECT)
        stored_rel_types = (
            {s.name for s in stored_profile.relation_vocabulary}
            if stored_profile is not None else set()
        )

        checks.append((
            "zéro LIE_A restant sur les slugs promus",
            not remaining_promoted_lie_a,
            f"{len(remaining_promoted_lie_a)} arête(s) restante(s)",
        ))
        if proposals:
            checks.append((
                "profil stocké version ≥ 1",
                stored_version is not None and stored_version >= 1,
                f"version={stored_version}",
            ))
            checks.append((
                "profil stocké porte les nouveaux RelationSpec",
                promoted_rel_types <= stored_rel_types,
                f"attendu ⊆ {promoted_rel_types}, stocké {stored_rel_types}",
            ))

        # ── Fiche 2 : ingérée avec le profil ÉVOLUÉ ──
        # Compte AVANT fiche 2 (après accept-all) — sert de base aux deltas
        # imputables à la fiche 2 (l'ingestion de fiche 1 a pu laisser des LIE_A
        # non promus, ex. clusters sous min_count).
        lie_a_before_fiche2, typed_before_fiche2 = rel_counts(relations_after_accept)

        report2 = await _ingest(driver, FICHE_2, profile)
        relations_after_fiche2 = await all_relations(driver, project=PROJECT)
        lie_a_after_fiche2, typed_after_fiche2 = rel_counts(relations_after_fiche2)

        lie_a_2 = lie_a_after_fiche2 - lie_a_before_fiche2
        typed_2 = typed_after_fiche2 - typed_before_fiche2
        ratio_2 = reuse_ratio(lie_a_2, typed_2)
        print(
            f"\nFiche 2 : {report2.entities_touched} entités, {lie_a_2} LIE_A "
            f"nouvelles, {typed_2} typées nouvelles, {report2.total_tokens} tokens"
        )

        # Toute arête écrite doit rester dans (vocab du profil ÉVOLUÉ UNION
        # {LIE_A, DESCRIBED_IN}) — garanti par construction (validate_relation
        # refuse tout le reste au write), vérifié ici sur le graphe réel.
        allowed = {s.name for s in profile.relation_vocabulary} | {NARRATIVE_REL, "DESCRIBED_IN"}
        outside = sorted({
            r["rel_type"] for r in relations_after_fiche2 if r["rel_type"] not in allowed
        })
        checks.append((
            "aucune arête hors du vocabulaire du profil évolué",
            not outside,
            f"types hors vocab : {outside}",
        ))

        # ── Bilan final ──
        print("\n===== BILAN =====")
        print(f"  tokens fiche 1 : {report1.total_tokens}  |  fiche 2 : {report2.total_tokens}")
        print(f"  propositions détectées : {len(proposals)}, acceptées : {len(proposals)}")
        print(f"  ratio de réutilisation (typé/(typé+LIE_A)) : "
              f"fiche 1 = {ratio_1:.0%}  →  fiche 2 = {ratio_2:.0%}")

        print("\n===== INVARIANTS =====")
        failed = 0
        for label, ok, detail in checks:
            print(f"  {'✓' if ok else '✗'} {label}" + ("" if ok else f"  → {detail}"))
            failed += not ok
        print(f"\n{'✓ E2E OK' if not failed else f'✗ {failed} invariant(s) cassé(s)'}")
        return 1 if failed else 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
