"""Session protest du bot B (atelier) — séparée de la session legacy.

Run:
    protest eval evals.atelier.session:session
    just evals-atelier

Ne pas lancer en même temps que `just evals` : les cas atelier wipent le
graphe Neo4j partagé avant chaque run.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from protest import From, ProTestSession, Use
from protest.evals import EvalCase, EvalSuite, ModelLabel, TaskResult

from evals._judge import FelixJudge
from evals.atelier.dataset import (
    BAPTEME_DIFFERE_INPUTS,
    CHECK_ACT_THEN_DEATH_INPUTS,
    CHECK_DEATH_THEN_ACT_INPUTS,
    FLASHBACK_CORRECTION_INPUTS,
    FLASHBACK_CREATION_INPUTS,
    GABARIT_AMBIANCE_INPUTS,
    SUBORDONNEE_CONTEXTE_INPUTS,
    SUBORDONNEE_FICHE_INPUTS,
    SUJET_APPOSITION_CONTEXTE_INPUTS,
    SUJET_APPOSITION_INPUTS,
    atelier_cases,
)
from evals.atelier.evaluators import multirun_majority

# Import runtime (pas TYPE_CHECKING) : protest résout les annotations des evals
# via get_type_hints — `TaskResult[AtelierRunResult]` doit être évaluable.
from evals.atelier.task import (
    AtelierRunResult,
    _bapteme_differe_check,
    _check_act_then_death,
    _check_death_then_act,
    _flashback_correction_check,
    _flashback_creation_check,
    _gabarit_ambiance_check,
    _subordonnee_contexte_check,
    _subordonnee_fiche_check,
    _sujet_apposition_check,
    _sujet_apposition_contexte_check,
    atelier_driver,
    run_atelier_case,
    run_atelier_multirun_case,
)
from felix.config import settings

if TYPE_CHECKING:
    from neo4j import AsyncDriver

atelier_model = ModelLabel(
    name=settings.llm_chat_model or settings.llm_model, provider="mistral"
)

session = ProTestSession(history=True)
session.bind(atelier_driver)

atelier_suite = EvalSuite("atelier", model=atelier_model, judge=FelixJudge())
session.add_suite(atelier_suite)


@atelier_suite.eval()
async def atelier(
    case: Annotated[EvalCase, From(atelier_cases)],
    driver: Annotated[AsyncDriver, Use(atelier_driver)],
) -> TaskResult[AtelierRunResult]:
    return await run_atelier_case(driver, case.inputs)


@atelier_suite.eval(evaluators=[multirun_majority(threshold=2, total=3)])
async def bapteme_differe(
    driver: Annotated[AsyncDriver, Use(atelier_driver)],
) -> TaskResult[AtelierRunResult]:
    """Multi-run (N=3, seuil ≥2/3) — variance Mistral Small, pas une régression code.

    Le cas est joué 3 fois en série ; vert si ≥2 passes réussissent. Chaque
    pass repart d'un graphe vide grâce au wipe intégré dans run_atelier_case.
    Aucune concurrence pour éviter les 429 de l'API Mistral."""
    return await run_atelier_multirun_case(
        driver,
        BAPTEME_DIFFERE_INPUTS,
        n=3,
        check=_bapteme_differe_check,
    )


@atelier_suite.eval(evaluators=[multirun_majority(threshold=2, total=3)])
async def check_death_then_act(
    driver: Annotated[AsyncDriver, Use(atelier_driver)],
) -> TaskResult[AtelierRunResult]:
    """Multi-run (N=3, seuil ≥2/3) — variance du juge Mistral Small.

    Mort-puis-agit : le juge doit détecter l'impossibilité temporelle (alerte).
    Joué 3 fois en série ; vert si ≥2 passes émettent l'alerte attendue."""
    return await run_atelier_multirun_case(
        driver,
        CHECK_DEATH_THEN_ACT_INPUTS,
        n=3,
        check=_check_death_then_act,
    )


@atelier_suite.eval(evaluators=[multirun_majority(threshold=2, total=3)])
async def check_act_then_death(
    driver: Annotated[AsyncDriver, Use(atelier_driver)],
) -> TaskResult[AtelierRunResult]:
    """Multi-run (N=3, seuil ≥2/3) — variance du juge Mistral Small.

    Agit-puis-mort : aucune alerte attendue (ordre chronologique normal).
    Joué 3 fois en série ; vert si ≥2 passes n'émettent pas d'alerte."""
    return await run_atelier_multirun_case(
        driver,
        CHECK_ACT_THEN_DEATH_INPUTS,
        n=3,
        check=_check_act_then_death,
    )


# ─────────── #56 / #57 : sur-extraction et sous-extraction ───────────────────────────


@atelier_suite.eval(evaluators=[multirun_majority(threshold=2, total=3)])
async def gabarit_ambiance(
    driver: Annotated[AsyncDriver, Use(atelier_driver)],
) -> TaskResult[AtelierRunResult]:
    """#56 : ambiance pure sans personnage nommé → 0 personnage inventé.

    Multi-run N=3 (seuil ≥2/3) : la variance Small sur ce type de cas est connue.
    Reproduction exacte du cas dogfood (« huis clos pétrolière, polar, surnaturel »).
    Vert si 0 entité personnage ET 0 prop biographique inventée."""
    return await run_atelier_multirun_case(
        driver,
        GABARIT_AMBIANCE_INPUTS,
        n=3,
        check=_gabarit_ambiance_check,
    )


@atelier_suite.eval(evaluators=[multirun_majority(threshold=2, total=3)])
async def subordonnee_fiche(
    driver: Annotated[AsyncDriver, Use(atelier_driver)],
) -> TaskResult[AtelierRunResult]:
    """#57 : personnage mentionné en subordonnée → sa fiche est créée.

    Multi-run N=3 (seuil ≥2/3) : la variance sur ce cas est le cœur du bug.
    Vert si les deux personnages existent : Lera (sujet) ET Fenn (mort mentionné)."""
    return await run_atelier_multirun_case(
        driver,
        SUBORDONNEE_FICHE_INPUTS,
        n=3,
        check=_subordonnee_fiche_check,
    )


@atelier_suite.eval(evaluators=[multirun_majority(threshold=2, total=3)])
async def sujet_apposition(
    driver: Annotated[AsyncDriver, Use(atelier_driver)],
) -> TaskResult[AtelierRunResult]:
    """#57 (variance) : sujet avec apposition → sa fiche est créée.

    Multi-run N=3 (seuil ≥2/3) : même structure que le cas Erick non reproductible
    à l'identique (variance inter-runs). Vert si la fiche de Haldren est présente."""
    return await run_atelier_multirun_case(
        driver,
        SUJET_APPOSITION_INPUTS,
        n=3,
        check=_sujet_apposition_check,
    )


@atelier_suite.eval(evaluators=[multirun_majority(threshold=2, total=3)])
async def sujet_apposition_contexte(
    driver: Annotated[AsyncDriver, Use(atelier_driver)],
) -> TaskResult[AtelierRunResult]:
    """#57 contextualisé : sujet + apposition au tour 2, working set chargé au tour 1.

    Reproduction de la structure exacte du dogfood Araïko : Karev (tour 1) charge
    le working set ; Ylden (tour 2) doit quand même recevoir sa fiche.
    Multi-run N=3 (seuil ≥2/3). Vert si la fiche d'Ylden est présente."""
    return await run_atelier_multirun_case(
        driver,
        SUJET_APPOSITION_CONTEXTE_INPUTS,
        n=3,
        check=_sujet_apposition_contexte_check,
    )


@atelier_suite.eval(evaluators=[multirun_majority(threshold=2, total=3)])
async def subordonnee_contexte(
    driver: Annotated[AsyncDriver, Use(atelier_driver)],
) -> TaskResult[AtelierRunResult]:
    """#57 contextualisé : subordonnée au tour 2, working set chargé au tour 1.

    Tour 1 crée Nara + Erkon (working set chargé). Tour 2 : Paya remplace Gorn
    (mort, mentionné en subordonnée). Vert si les deux fiches existent.
    Multi-run N=3 (seuil ≥2/3)."""
    return await run_atelier_multirun_case(
        driver,
        SUBORDONNEE_CONTEXTE_INPUTS,
        n=3,
        check=_subordonnee_contexte_check,
    )


# ─────────────────── #44 : raconter dans le désordre ────────────────────────────────


@atelier_suite.eval(evaluators=[multirun_majority(threshold=2, total=3)])
async def flashback_correction(
    driver: Annotated[AsyncDriver, Use(atelier_driver)],
) -> TaskResult[AtelierRunResult]:
    """#44 cas cirque : correction de l'ordre d'un événement existant (move_event).

    Beat 1 : Jovan meurt. Beat 2 : event postérieur impliquant Jovan (juge alertera).
    Beat 3 : « l'annonce de Kezra c'était la veille de la mort de Jovan, je raconte
    dans le désordre » → move_event doit replacer l'annonce AVANT la mort.
    Vert si ordre(annonce) < ordre(mort), seuil ≥2/3."""
    return await run_atelier_multirun_case(
        driver,
        FLASHBACK_CORRECTION_INPUTS,
        n=3,
        check=_flashback_correction_check,
    )


@atelier_suite.eval(evaluators=[multirun_majority(threshold=2, total=3)])
async def flashback_creation(
    driver: Annotated[AsyncDriver, Use(atelier_driver)],
) -> TaskResult[AtelierRunResult]:
    """#44 cas pétrolier : flashback explicite à la création (add_event avec avant=).

    Beat 1 : Imra arrive. Beat 2 : « la tempête trois jours avant l'arrivée d'Imra,
    je raconte dans le désordre » → add_event avec avant='arrivée d'Imra'.
    Vert si ordre(tempête) < ordre(arrivée Imra), seuil ≥2/3."""
    return await run_atelier_multirun_case(
        driver,
        FLASHBACK_CREATION_INPUTS,
        n=3,
        check=_flashback_creation_check,
    )
