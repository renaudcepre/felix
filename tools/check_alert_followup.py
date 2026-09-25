"""Sonde LLM — relâche d'alerte au tour suivant (#50-a) : critère de done.

Vérifie que si une :Alert non-notifiée est en base, le maître la mentionne
sobrement dans sa prochaine réplique (« au tour suivant Felix relève
l'incohérence ») ET que l'alerte est marquée notified après le tour.

Scénario joué : un personnage nommé Korvax a été tué dans le récit ; une alerte
de cohérence a été émise (« Korvax ne peut pas agir ici : il est mort au
chapitre précédent »). L'auteur continue en ignorant la mort (« Korvax ouvre la
porte et entre dans la salle. »). Felix doit signaler l'incohérence possible en
une phrase sobre.

La route SSE n'est PAS lancée : on reproduit en code la logique de _master_prompt
(consume_unnotified_alerts → render_alerts_block) et on appelle le maître réel
via build_master_agent (pattern de evals/atelier/master_ab.py).

Usage : uv run python tools/check_alert_followup.py
"""

# ruff: noqa: T201
from __future__ import annotations

import asyncio

from felix.atelier.agent import ATELIER_CHOICES, build_master_agent
from felix.core import GenericDeps
from felix.core.alerts import (
    consume_unnotified_alerts,
    record_alert,
    render_alerts_block,
)
from felix.graph.driver import get_driver, setup_constraints

CHOICE = ATELIER_CHOICES["scenario"]

# Projet isolé — noms inédits dans tous les prompts.
PROJ = "sonde-alert-followup"

# Alerte posée comme si le checker venait de la détecter en fin de tour précédent.
ALERT_BODY = "Korvax ne peut pas agir ici : il est mort au chapitre précédent"

# Message neutre de l'auteur qui IGNORE la mort (le cas à détecter).
AUTHOR_MSG = "Korvax ouvre la porte et entre dans la salle."

# Mots-clés attendus dans la réplique : nom du perso + signal d'incohérence.
# Tolérant au phrasé : mort/tué/déjà/incohérence/impossible/contradict…
_PERSO_KW = "korvax"
_SIGNAL_KW = (
    "mort",
    "tué",
    "déjà",
    "incohérence",
    "impossible",
    "contradi",
    "anachroni",
    "disparu",
    "flash-back",
    "flash",
)

N = 3
THRESHOLD = 2


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


async def _run_with_backoff(make_coro, attempts: int = 3) -> object:
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


def _reply_mentions_incoherence(reply: str) -> bool:
    """Vrai si la réplique cite le perso ET donne un signal d'incohérence."""
    low = reply.lower()
    return _PERSO_KW in low and any(kw in low for kw in _SIGNAL_KW)


async def _clean(driver) -> None:
    async with driver.session() as session:
        await session.run("MATCH (a:Alert {project: $p}) DETACH DELETE a", p=PROJ)
        await session.run("MATCH (n:GenEntity {project: $p}) DETACH DELETE n", p=PROJ)


async def run_once(driver) -> bool:
    """Un run : pose l'alerte, joue UN tour du maître, vérifie."""
    await _clean(driver)

    # 1. Pose l'alerte comme si le checker l'avait émise en fin de tour précédent.
    await record_alert(driver, ALERT_BODY, project=PROJ)

    # 2. Reproduit exactement _master_prompt de la route SSE : consume + render.
    alert_bodies = await consume_unnotified_alerts(driver, project=PROJ)
    alerts_block = render_alerts_block(alert_bodies)
    prefixed_msg = f"{alerts_block}\n\n{AUTHOR_MSG}" if alerts_block else AUTHOR_MSG

    # 3. Joue le maître réel (build_master_agent — même config qu'en prod).
    agent = build_master_agent(CHOICE)
    deps = GenericDeps(driver=driver, profile=CHOICE.profile, project_id=PROJ)
    result = await _run_with_backoff(lambda: agent.run(prefixed_msg, deps=deps))
    reply = (result.output or "").strip()  # type: ignore[union-attr]
    print(f"    felix  : {reply[:200]!r}")

    # 4. Critères de succès.
    mentioned = _reply_mentions_incoherence(reply)
    # L'alerte est déjà marquée notified par consume_unnotified_alerts ci-dessus
    # (read-and-mark atomique) — on vérifie quand même pour être complet.
    async with driver.session() as session:
        res = await session.run(
            "MATCH (a:Alert {project: $p}) RETURN a.notified AS n", p=PROJ
        )
        rows = await res.data()
    notified = bool(rows) and all(r["n"] for r in rows)

    if not mentioned:
        print("    ✗ la réplique ne mentionne pas l'incohérence")
    if not notified:
        print(f"    ✗ l'alerte n'est pas marquée notified (rows={rows})")

    return mentioned and notified


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

        ok_final = passes >= THRESHOLD
        print(
            f"\n{'✓' if ok_final else '✗'} alerte relâchée au tour suivant"
            f" — {passes}/{N} passes (seuil {THRESHOLD}/{N})"
        )
        return 0 if ok_final else 1

    finally:
        await _clean(driver)
        await driver.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
