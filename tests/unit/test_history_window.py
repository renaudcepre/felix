"""Fenêtrage de l'historique LLM par budget de tokens — garanties STRUCTURELLES.

Test déterministe (sans LLM) de la fonction pure `window_history_by_tokens` :
Felix threade tout l'historique à chaque tour → l'input croît sans fin. On borne
en gardant les tours les plus RÉCENTS sous un budget, le graphe servant de mémoire
longue. Invariants vérifiés ici :
- sous budget → liste renvoyée inchangée (no-op) ;
- budget serré → seuls les tours récents sont gardés, dans l'ordre ;
- le dernier tour est TOUJOURS gardé, même s'il dépasse seul le budget ;
- on coupe UNIQUEMENT sur une frontière de tour → jamais de ToolReturnPart orphelin
  (chaque ToolReturnPart gardé a son ToolCallPart) ;
- estimate_tokens croît avec la taille du contenu.
"""
from __future__ import annotations

from protest import ProTestSuite
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from felix.api.history import estimate_tokens, window_history_by_tokens

history_window_suite = ProTestSuite("HistoryWindow")


def _user_turn(prompt: str, reply: str) -> list:
    """Un tour simple : requête utilisateur → réponse texte du modèle."""
    return [
        ModelRequest(parts=[UserPromptPart(content=prompt)]),
        ModelResponse(parts=[TextPart(content=reply)]),
    ]


def _tool_turn(prompt: str, tool: str, tcid: str, result: str, reply: str) -> list:
    """Un tour avec appel d'outil : la paire ToolCallPart/ToolReturnPart vit DANS le tour.

    Le ToolReturnPart arrive dans un ModelRequest SANS UserPromptPart → ce n'est pas
    une frontière de tour, donc il reste collé à son ToolCallPart au fenêtrage.
    """
    return [
        ModelRequest(parts=[UserPromptPart(content=prompt)]),
        ModelResponse(parts=[ToolCallPart(tool_name=tool, args={"q": prompt}, tool_call_id=tcid)]),
        ModelRequest(parts=[ToolReturnPart(tool_name=tool, content=result, tool_call_id=tcid)]),
        ModelResponse(parts=[TextPart(content=reply)]),
    ]


def _turn_starts(messages: list) -> int:
    """Compte les frontières de tour (ModelRequest contenant un UserPromptPart)."""
    return sum(
        1
        for m in messages
        if isinstance(m, ModelRequest) and any(isinstance(p, UserPromptPart) for p in m.parts)
    )


@history_window_suite.test()
def test_under_budget_returns_unchanged() -> None:
    """Historique déjà sous le budget → renvoyé tel quel (no-op)."""
    messages = [*_user_turn("salut", "bonjour"), *_user_turn("ça va ?", "oui")]
    out = window_history_by_tokens(messages, budget=100_000)
    assert out == messages


@history_window_suite.test()
def test_empty_history_is_noop() -> None:
    """Liste vide → liste vide (pas d'erreur)."""
    assert window_history_by_tokens([], budget=8000) == []


@history_window_suite.test()
def test_keeps_only_recent_turns_under_budget() -> None:
    """Budget serré → on ne garde que les tours les plus récents qui rentrent."""
    # 5 tours d'environ ~25 tokens chacun (100 chars / 4).
    body = "x" * 100
    turns = [_user_turn(f"message {i} {body}", f"réponse {i} {body}") for i in range(5)]
    messages = [m for turn in turns for m in turn]
    # Budget qui ne tient ~que 2 tours.
    per_turn = sum(estimate_tokens(m) for m in turns[0])
    out = window_history_by_tokens(messages, budget=int(per_turn * 2.5))
    kept = _turn_starts(out)
    assert kept == 2, f"attendu 2 tours gardés, obtenu {kept}"
    # Ce sont bien les DERNIERS (le tour le plus récent est présent).
    assert messages[-1] in out
    assert messages[-2] in out
    # Le tout premier tour a été coupé.
    assert messages[0] not in out


@history_window_suite.test()
def test_always_keeps_last_turn_even_when_oversize() -> None:
    """Le dernier tour dépasse seul le budget → on le garde quand même (jamais vide)."""
    huge = "y" * 4000  # ~1000 tokens à lui seul
    messages = [*_user_turn("vieux", "vieux"), *_user_turn(huge, "ok")]
    out = window_history_by_tokens(messages, budget=10)
    assert _turn_starts(out) == 1
    assert messages[-2] in out  # le UserPromptPart énorme du dernier tour
    assert out  # non vide


@history_window_suite.test()
def test_no_orphan_tool_return() -> None:
    """Couper sur une frontière de tour ne sépare JAMAIS un ToolReturnPart de son ToolCallPart."""
    old = _user_turn("vieux tour à jeter " + "z" * 200, "ok")
    recent = _tool_turn("cherche Nora", "find_entity", "call-1", '{"name":"Nora"}', "trouvée")
    messages = [*old, *recent]
    # Budget qui ne garde que le tour récent (avec l'appel d'outil).
    per_old = sum(estimate_tokens(m) for m in old)
    out = window_history_by_tokens(messages, budget=per_old - 1)
    # Chaque ToolReturnPart gardé doit avoir un ToolCallPart de même tool_call_id.
    call_ids = {
        p.tool_call_id
        for m in out
        if isinstance(m, ModelResponse)
        for p in m.parts
        if isinstance(p, ToolCallPart)
    }
    return_ids = {
        p.tool_call_id
        for m in out
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart)
    }
    assert return_ids, "le tour récent (avec outil) doit être gardé"
    assert return_ids <= call_ids, f"ToolReturnPart orphelin : {return_ids - call_ids}"


@history_window_suite.test()
def test_estimate_tokens_grows_with_content() -> None:
    """estimate_tokens croît avec la taille du contenu."""
    small = ModelRequest(parts=[UserPromptPart(content="court")])
    big = ModelRequest(parts=[UserPromptPart(content="long " * 500)])
    assert estimate_tokens(big) > estimate_tokens(small)


@history_window_suite.test()
def test_estimate_counts_tool_call_and_return() -> None:
    """L'estimation inclut les args d'outils et le contenu des ToolReturnPart (pas que le texte)."""
    call = ModelResponse(
        parts=[ToolCallPart(tool_name="add_entity", args={"name": "Nora " * 100}, tool_call_id="c")]
    )
    ret = ModelRequest(
        parts=[ToolReturnPart(tool_name="add_entity", content="résultat " * 100, tool_call_id="c")]
    )
    assert estimate_tokens(call) > 0
    assert estimate_tokens(ret) > 0
