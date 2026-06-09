"""Fenêtrage de l'historique LLM par budget de tokens.

Felix threade tout l'historique de conversation à chaque tour (la route SSE renvoie
les `all_messages()` au front, qui les re-renvoie au tour suivant). L'input croît donc
linéairement avec le nombre de tours → coût et contexte explosent sur un projet long.

Or Felix a DEUX mémoires : le fil de chat (coûteux) et le graphe/bible (durable,
relisible via list_entities/find_entity). On borne donc le fil par budget de tokens :
on garde les tours les plus RÉCENTS (cohérence conversationnelle) et on laisse le
graphe fournir les faits anciens. Coût/tour plat quelle que soit la durée du projet.

Fonctions PURES (sans I/O, sans LLM, sans Neo4j) → testables en isolation.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic_ai.messages import (
    ModelRequest,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage, ModelRequestPart, ModelResponsePart


def _coerce_text(value: object) -> str:
    """Texte d'un contenu hétérogène (str direct, sinon JSON compact)."""
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str, ensure_ascii=False)


def _part_text(part: ModelRequestPart | ModelResponsePart) -> str:
    """Texte facturable approximatif d'une part — ce qui pèse réellement en tokens."""
    if isinstance(part, (UserPromptPart, SystemPromptPart, TextPart, RetryPromptPart)):
        return _coerce_text(part.content)
    if isinstance(part, ToolCallPart):
        return part.tool_name + _coerce_text(part.args)
    if isinstance(part, ToolReturnPart):
        return part.tool_name + _coerce_text(part.content)
    return str(part)


def estimate_tokens(msg: ModelMessage) -> int:
    """Estimation grossière du coût en tokens d'un message (≈ chars/4).

    Approximation suffisante pour un budget : on ne facture pas exactement et on
    évite toute dépendance à un tokenizer. Couvre le texte, les args d'outils et le
    contenu des ToolReturnPart (les vrais moteurs de coût quand l'historique grossit).
    """
    text = "".join(_part_text(p) for p in msg.parts)
    return len(text) // 4


def _is_turn_start(msg: ModelMessage) -> bool:
    """Frontière de tour : un ModelRequest qui porte un prompt utilisateur.

    Les ToolReturnPart d'un même tour arrivent dans des ModelRequest SANS
    UserPromptPart → ils ne sont pas des frontières, donc restent collés à leur
    ToolCallPart. Couper uniquement ici garantit l'absence de ToolReturnPart orphelin.
    """
    return isinstance(msg, ModelRequest) and any(
        isinstance(p, UserPromptPart) for p in msg.parts
    )


def window_history_by_tokens(
    messages: list[ModelMessage], budget: int
) -> list[ModelMessage]:
    """Garde les tours les plus récents dont le cumul de tokens tient sous `budget`.

    - Découpe en tours sur les frontières `_is_turn_start` (paires tool intactes).
    - Parcourt du plus récent au plus ancien, garde tant que le cumul ≤ budget.
    - Garde TOUJOURS au moins le dernier tour (même s'il dépasse seul le budget).
    - Déjà sous le budget (rien à couper) → renvoie la liste inchangée.
    """
    if not messages:
        return messages

    # Découpe en tours. Tout message précédant le 1er prompt utilisateur (cas
    # défensif) forme un groupe initial, traité comme le plus ancien.
    turns: list[list[ModelMessage]] = []
    current: list[ModelMessage] = []
    for msg in messages:
        if _is_turn_start(msg) and current:
            turns.append(current)
            current = []
        current.append(msg)
    if current:
        turns.append(current)

    kept: list[list[ModelMessage]] = []
    total = 0
    for turn in reversed(turns):
        turn_tokens = sum(estimate_tokens(m) for m in turn)
        # `kept` non vide → le dernier tour est déjà gardé : on peut s'arrêter.
        if kept and total + turn_tokens > budget:
            break
        kept.append(turn)
        total += turn_tokens
    kept.reverse()

    if len(kept) == len(turns):
        return messages  # rien coupé → no-op
    return [msg for turn in kept for msg in turn]
