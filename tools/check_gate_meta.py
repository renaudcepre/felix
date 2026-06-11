"""Sonde LLM — registre MÉTA au gate (issue #69) : critère de done.

Le dogfood 2026-06-11 a montré le gate router la conversation SUR l'outil comme
du récit : « tu mets pas à jour mon âge ? tu as écrit 32 » → {"fait": "l'âge du
personnage est 33", "noter": true} — fait recalculé de tête, cascade d'alertes.

Cette sonde appelle build_gate_agent() en direct (stateless, 1 appel/cas) et
vérifie les deux lois de #69 :
- le registre MÉTA (remarque/question sur la fiche, plan de narration) est MUET ;
- quand on note, le `fait` est VERBATIM : jamais d'âge calculé depuis une année,
  jamais de chiffre qui n'est pas dans le message.

Univers Romeck/Lioba/Carstier/Madra — absent de tous les prompts (anti-leakage).

Usage : uv run python tools/check_gate_meta.py
"""
# ruff: noqa: T201
from __future__ import annotations

import asyncio
import re

from felix.atelier.agent import build_gate_agent

N = 3  # runs par cas ; un cas est vert à la majorité (≥ MAJORITY/N)
MAJORITY = 2

# (label, message, noter_attendu, fragment_obligatoire_du_fait, regex_interdit_du_fait)
CASES: list[tuple[str, str, bool, str | None, str | None]] = [
    (
        "remarque sur la fiche sans valeur corrigée → muet",
        "tu mets pas à jour l'âge dans la fiche de Romeck ? tu as écrit 52",
        False, None, None,
    ),
    (
        "question sur ce qui est noté → muet",
        "pourquoi tu as noté « borgne » sur la fiche de Lioba ?",
        False, None, None,
    ),
    (
        "plan de narration (parler de…) → muet",
        "ce qui serait intéressant dans cette histoire, ce serait de parler "
        "de la jeunesse de Romeck",
        False, None, None,
    ),
    (
        "correction sèche avec la valeur → notée, valeur verbatim",
        "non, Lioba a 67 ans",
        True, "67", None,
    ),
    (
        "année de naissance → fait verbatim, JAMAIS d'âge calculé",
        "Romeck, le veilleur du port de Carstier, est né en 1962",
        True, "1962", r"\b\d{2}\s*ans\b",
    ),
    (
        "contrôle positif : récit normal → noté",
        "Madra, la patronne de la halle aux grains, surveille Romeck "
        "depuis des semaines",
        True, "madra", None,
    ),
]


def _is_transient(exc: Exception) -> bool:
    """Détecte les erreurs réseau/API récupérables (même logique que evals._utils)."""
    if isinstance(exc, TimeoutError):
        return True
    if "timeout" in type(exc).__qualname__.lower():
        return True
    msg = str(exc).lower()
    return any(p in msg for p in (
        "429", "rate", "timeout", "500", "502", "503", "504", "invalid_function_call",
    ))


async def _run_gate(agent, message: str, attempts: int = 3):
    delay = 3.0
    last: Exception | None = None
    for _ in range(attempts):
        try:
            return await agent.run(message)
        except Exception as exc:
            if not _is_transient(exc):
                raise
            last = exc
            print(f"    ↻ transient ({type(exc).__name__}), retry dans {delay:.0f}s…")
            await asyncio.sleep(delay)
            delay *= 2
    raise last  # type: ignore[misc]


def _verdict(
    decision, expect_noter: bool, must_contain: str | None, must_not: str | None
) -> tuple[bool, str]:
    fait = decision.fait or ""
    if decision.noter is not expect_noter:
        return False, f"noter={decision.noter} (attendu {expect_noter}), fait={fait!r}"
    if expect_noter and must_contain and must_contain.lower() not in fait.lower():
        return False, f"fait sans «{must_contain}» : {fait!r}"
    if expect_noter and must_not and re.search(must_not, fait):
        return False, f"fait avec motif interdit {must_not} : {fait!r}"
    return True, fait


async def main() -> int:
    agent = build_gate_agent()
    failed_cases = 0
    for label, message, expect_noter, must_contain, must_not in CASES:
        print(f"\n── {label}\n   «{message[:74]}»")
        passes = 0
        for i in range(1, N + 1):
            result = await _run_gate(agent, message)
            ok, detail = _verdict(result.output, expect_noter, must_contain, must_not)
            passes += ok
            print(f"   [{i}/{N}] {'✓' if ok else '✗'} {detail[:90]}")
        ok_case = passes >= MAJORITY
        failed_cases += not ok_case
        print(f"   → {'PASS' if ok_case else 'FAIL'} ({passes}/{N})")

    total = len(CASES)
    print(f"\n{total - failed_cases}/{total} cas verts")
    return 1 if failed_cases else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
