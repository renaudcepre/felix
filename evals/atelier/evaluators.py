"""Evaluators de la suite atelier — symboliques, sur l'état du graphe.

ctx.output est un AtelierRunResult (answer + characters + cards).
Matching d'IDs volontairement souple (substring sur id/nom normalisés) —
leçon des evals pipeline : le match exact de sets génère des faux négatifs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from protest.evals import EvalContext, Metric, Reason, Verdict, evaluator

from evals._utils import normalize


def _char_keys(ctx: EvalContext) -> list[str]:
    """Clés normalisées (id + nom) des personnages présents dans le graphe."""
    keys = []
    for char in ctx.output.characters:
        keys.append(normalize(str(char.get("id", ""))))
        keys.append(normalize(str(char.get("name", ""))))
    return keys


@dataclass
class GraphCharsResult:
    char_recall: Annotated[float, Metric]
    chars_ok: Annotated[bool, Verdict]
    missing_chars: Annotated[str, Reason] = ""


@evaluator
def graph_has_characters(ctx: EvalContext, ids: str = "") -> GraphCharsResult:
    """Chaque id attendu (CSV) doit matcher un personnage du graphe (substring)."""
    expected = [normalize(e.strip()) for e in ids.split(",") if e.strip()]
    keys = _char_keys(ctx)
    matched = [e for e in expected if any(e in k or k in e for k in keys if k)]
    score = len(matched) / len(expected) if expected else 1.0
    missing = [e for e in expected if e not in matched]
    return GraphCharsResult(
        char_recall=score,
        chars_ok=score == 1.0,
        missing_chars=", ".join(missing),
    )


@dataclass
class CharCountResult:
    char_count: Annotated[float, Metric]
    count_ok: Annotated[bool, Verdict]
    count_detail: Annotated[str, Reason] = ""


@evaluator
def graph_char_count(ctx: EvalContext, n: int = 0) -> CharCountResult:
    """Le graphe doit contenir exactement n personnages (anti-doublon, anti-zèle)."""
    actual = len(ctx.output.characters)
    names = ", ".join(str(c.get("name")) for c in ctx.output.characters)
    return CharCountResult(
        char_count=float(actual),
        count_ok=actual == n,
        count_detail=f"attendu {n}, trouvé {actual} ({names})" if actual != n else "",
    )


@evaluator
def no_tool_cards(ctx: EvalContext) -> bool:
    """Aucune carte tool ne doit avoir été émise (cas lecture seule / smalltalk)."""
    return not ctx.output.cards


@dataclass
class CardsResult:
    cards_ok: Annotated[bool, Verdict]
    cards_detail: Annotated[str, Reason] = ""


@evaluator
def cards_for_subjects(ctx: EvalContext, subjects: str = "") -> CardsResult:
    """Une carte tool doit exister pour chaque sujet attendu (CSV, match souple)."""
    expected = [normalize(s.strip()) for s in subjects.split(",") if s.strip()]
    actual = [normalize(c.get("subject", "")) for c in ctx.output.cards]
    missing = [e for e in expected if not any(e in a or a in e for a in actual)]
    return CardsResult(
        cards_ok=not missing,
        cards_detail=f"cartes manquantes : {', '.join(missing)}" if missing else "",
    )


@dataclass
class AlertResult:
    alert_ok: Annotated[bool, Verdict]
    alert_detail: Annotated[str, Reason] = ""


@evaluator
def alert_emitted(ctx: EvalContext, expected: bool = True) -> AlertResult:
    """Le check de cohérence doit (ou non) émettre une alerte : la route SSE
    déclenche l'alerte ssi le verdict conclut à une contradiction."""
    alert = ctx.output.alert
    if alert is None:
        return AlertResult(alert_ok=False, alert_detail="check non exécuté")
    fired = bool(alert.get("contradiction"))
    return AlertResult(
        alert_ok=fired == expected,
        alert_detail=alert.get("reason", ""),
    )


@dataclass
class AnswerResult:
    answer_score: Annotated[float, Metric]
    answer_ok: Annotated[bool, Verdict]
    answer_missing: Annotated[str, Reason] = ""


@evaluator
def answer_mentions(ctx: EvalContext, facts: str = "", min_score: float = 1.0) -> AnswerResult:
    """La réponse texte doit mentionner chaque fait attendu (CSV)."""
    expected = [normalize(f.strip()) for f in facts.split(",") if f.strip()]
    answer = normalize(ctx.output.answer)
    matched = [e for e in expected if e in answer]
    score = len(matched) / len(expected) if expected else 1.0
    missing = [e for e in expected if e not in matched]
    return AnswerResult(
        answer_score=score,
        answer_ok=score >= min_score,
        answer_missing=", ".join(missing),
    )
