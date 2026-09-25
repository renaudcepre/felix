"""Sonde LLM — correction de type (issue #75) : critère de done.

Rejoue le cas Klarkz du dogfood 2026-06-12 : une entité rangée sous le mauvais
type, l'auteur corrige (« X n'est pas un lieu, c'est un minerai »). Avant #75,
aucun chemin d'exécution : les modèles bricolaient une prop `type=...` et le
checker alertait en boucle. Vert si la passe 1 utilise retype_entity : le
`entity_type` change EN BASE (et plus aucune prop `type*` parasite).

Univers Vorvane — frais, absent de tous les prompts (anti-leakage).

Usage : uv run python tools/check_retype.py
"""

# ruff: noqa: T201
from __future__ import annotations

import asyncio

from felix.atelier.agent import create_atelier_agent
from felix.atelier.deps import AtelierDeps
from felix.core import SCENARIO_PROFILE, all_entities
from felix.graph.driver import get_driver, setup_constraints

PROJ = "sonde-retype"
BEAT = (
    "pardon, je me suis trompé : le Vorvane n'est pas un lieu, "
    "c'est un minerai rare et instable."
)
N = 3
MAJORITY = 2


def _is_transient(exc: Exception) -> bool:
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
    async with driver.session() as session:
        await session.run("MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=PROJ)
        await session.run(
            "MERGE (e:GenEntity {id: 'vorvane', project: $p})"
            " SET e.name = 'Vorvane', e.entity_type = 'lieu'",
            p=PROJ,
        )

    deps = AtelierDeps(driver=driver, profile=SCENARIO_PROFILE, project_id=PROJ)
    agent = create_atelier_agent()
    await _run_agent(lambda: agent.run(BEAT, deps=deps))

    entities = await all_entities(driver, project=PROJ)
    vorvane = next((e for e in entities if str(e.get("id", "")) == "vorvane"), None)
    if vorvane is None:
        print("    ✗ Vorvane a disparu de la base")
        return False
    etype = str(vorvane.get("entity_type", "?"))
    type_props = {
        k: v for k, v in vorvane.items() if "type" in k.lower() and k != "entity_type"
    }
    ok = etype != "lieu" and not type_props
    detail = f"entity_type={etype!r}" + (
        f", props parasites {type_props}" if type_props else ""
    )
    print(f"    {'✓' if ok else '✗'} {detail}")
    return ok


async def main() -> int:
    driver = get_driver()
    await setup_constraints(driver)
    passes = 0
    try:
        for i in range(1, N + 1):
            print(f"\n[pass {i}/{N}]")
            passes += await run_once(driver)
        ok = passes >= MAJORITY
        print(
            f"\n{'✓' if ok else '✗'} correction de type : {passes}/{N} passes (seuil {MAJORITY}/{N})"
        )
        return 0 if ok else 1
    finally:
        async with driver.session() as session:
            await session.run(
                "MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=PROJ
            )
        await driver.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
