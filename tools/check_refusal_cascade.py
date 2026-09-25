"""Sonde LLM — refus en cascade (issue #59) : critère de done.

Vérifie que le LLM ne contourne plus la garde « evenement » en re-tentant
add_entity sous un autre type.

Beat joué 3 fois : un récit mentionnant explicitement « la bataille de Valcrest »
entre deux groupes. Vert si 0 entité de type NON-événement portant « bataille »
dans le nom n'est présente en base. Un nœud evenement (add_event) est attendu
et toléré : c'est la chronologie, pas le contournement.

Usage : uv run python tools/check_refusal_cascade.py
"""

# ruff: noqa: T201
from __future__ import annotations

import asyncio

from felix.atelier.agent import (
    create_atelier_agent,
    create_chronicle_agent,
    create_relation_agent,
)
from felix.atelier.deps import AtelierDeps
from felix.core import SCENARIO_PROFILE, all_entities
from felix.graph.driver import get_driver, setup_constraints

# Projet isolé — noms inédits dans tous les prompts.
PROJ = "sonde-refusal-cascade"

# Beat délibérément ambigu : « la bataille de Valcrest » sonne comme une entité,
# mais c'est un événement. Le LLM ne doit PAS l'enregistrer en entité.
BEAT = (
    "La bataille de Valcrest fait rage entre les Forgerons du Cœur "
    "et les Gardiens de l'Ombre. Des centaines de soldats tombent."
)
N = 3

checks: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    checks.append((label, ok, detail))
    print(
        f"{'✓' if ok else '✗'} {label}" + (f" — {detail}" if detail and not ok else "")
    )


def _is_transient(exc: Exception) -> bool:
    """Détecte les erreurs réseau/API récupérables (même logique que evals._utils)."""
    if isinstance(exc, TimeoutError):
        return True
    if "timeout" in type(exc).__qualname__.lower():
        return True
    msg = str(exc).lower()
    return any(
        p in msg
        for p in (
            "429",
            "rate",
            "timeout",
            "500",
            "502",
            "503",
            "504",
            "invalid_function_call",
        )
    )


async def _run_agent(make_coro, attempts: int = 3) -> object:
    """Relance sur les transients Mistral (429, 5xx, timeout) — backoff exponentiel."""
    delay = 3.0
    last: Exception | None = None
    for _ in range(attempts):
        try:
            return await make_coro()
        except Exception as exc:
            if not _is_transient(exc):
                raise
            last = exc
            print(f"    ↻ transient ({type(exc).__name__}), retry dans {delay:.0f}s…")
            await asyncio.sleep(delay)
            delay *= 2
    raise last  # type: ignore[misc]


async def run_once(driver) -> bool:
    """Un run : wipe du projet sonde, 3 passes agent, lecture de la base."""
    async with driver.session() as session:
        await session.run(
            "MATCH (n:GenEntity) WHERE n.project = $p DETACH DELETE n", p=PROJ
        )

    deps = AtelierDeps(driver=driver, profile=SCENARIO_PROFILE, project_id=PROJ)

    agent = create_atelier_agent()
    relation_agent = create_relation_agent()
    chronicle_agent = create_chronicle_agent()

    await _run_agent(lambda: agent.run(BEAT, deps=deps))
    await _run_agent(lambda: relation_agent.run(BEAT, deps=deps, message_history=None))
    await _run_agent(lambda: chronicle_agent.run(BEAT, deps=deps, message_history=None))

    entities = await all_entities(driver, project=PROJ)

    # Un nœud evenement créé par add_event (entity_type='evenement') est ATTENDU
    # et ne compte pas comme un contournement.
    bataille_non_event = [
        e
        for e in entities
        if "bataille" in str(e.get("name", "")).lower()
        and str(e.get("entity_type", "")).lower() != "evenement"
    ]

    if bataille_non_event:
        types = [e.get("entity_type") for e in bataille_non_event]
        print(f"    ✗ entité(s) 'bataille' non-événement en base : {types}")
    else:
        all_names = [e.get("name", "?") for e in entities]
        print(
            f"    ✓ aucune entité 'bataille' non-événement "
            f"({len(entities)} entité(s) totale(s) : {all_names[:6]})"
        )

    return len(bataille_non_event) == 0


async def main() -> int:
    driver = get_driver()
    await setup_constraints(driver)
    passes = 0
    try:
        for i in range(1, N + 1):
            print(f"\n[pass {i}/{N}]")
            ok = await run_once(driver)
            passes += ok
            print(f"  → {'PASS' if ok else 'FAIL'}")

        check(
            "refus cascade : 0 entité « bataille » non-événement",
            passes == N,
            f"{passes}/{N} passes",
        )

        failed = [label for label, ok, _ in checks if not ok]
        print(
            f"\n{len(checks) - len(failed)}/{len(checks)} checks verts  ({passes}/{N} passes)"
        )
        return 1 if failed else 0

    finally:
        async with driver.session() as session:
            await session.run(
                "MATCH (n:GenEntity) WHERE n.project = $p DETACH DELETE n", p=PROJ
            )
        await driver.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
