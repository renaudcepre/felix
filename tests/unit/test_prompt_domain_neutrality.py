"""Domain neutrality of the prompts: fiction vocabulary belongs to `scenario` only.

Felix started as a screenplay copilot. The shared prompts (extractors, linker,
master, gate, checker, tool docstrings, context blocks) kept talking about
characters, deaths and flash-backs to a maintenance technician. This suite
renders every LLM-facing text an atelier choice actually sends, and checks that
no choice other than `scenario` carries a word of the fiction stoplist.

Test universe: none needed (pure rendering, no LLM, no Neo4j). Never copy the
prompt-only example universe here — cf. [[feedback_prompt_test_leakage]].
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from protest import ProTestSuite

from felix.atelier.agent import ATELIER_CHOICES, RouteDecision, build_turn_agents
from felix.core.alerts import render_alerts_block
from felix.core.check import SOURCE_VERIFY_PROMPT, render_check_prompt
from felix.core.graph import render_recent_block
from felix.core.profile import (
    EMERGENT_SEED_PROFILE,
    MAINTENANCE_PROFILE,
    SCENARIO_PROFILE,
    runs_chronicle,
)
from felix.core.tools import check_add_entity_guards
from felix.core.user_edits import render_user_edits_block

if TYPE_CHECKING:
    from felix.atelier.agent import AgentChoice

prompt_domain_neutrality_suite = ProTestSuite("PromptDomainNeutrality")

# Whole words only: « hauteur » is a legit dimension key, « auteur » is not.
STOPLIST = re.compile(
    r"\b(?:sc[ée]narios?|histoires?|r[ée]cits?|personnages?|chapitres?|auteurs?"
    r"|bibles?|intrigues?|flash-?backs?|morts?|vivants?|h[ée]ros)\b",
    re.IGNORECASE,
)

_CONTEXT = "Entité A (id: a, type: t)\nPropriétés : x=1"
_WRITES = "- a.x = '1' (nouveau)"


def _agent_text(agent: Any) -> str:
    """Instructions + every tool description and JSON schema of an Agent — what
    pydantic-ai actually sends, inspected without any network call."""
    parts = ["".join(agent._instructions)]
    for tool in agent._function_toolset.tools.values():
        parts.append(tool.description or "")
        parts.append(json.dumps(tool.function_schema.json_schema, ensure_ascii=False))
    return "\n".join(parts)


def rendered_prompts(choice: AgentChoice) -> dict[str, str]:
    """Every LLM-facing text of a choice, keyed by pass. The chronicle pass is
    left out when the profile keeps no chronology: it is built but never run."""
    profile = choice.profile
    turn = build_turn_agents(choice, profile)
    chronology = runs_chronicle(profile)
    texts = {
        "master": _agent_text(turn.master),
        "gate": _agent_text(turn.gate)
        + json.dumps(RouteDecision.model_json_schema(), ensure_ascii=False),
        "atelier": _agent_text(turn.atelier),
        "relation": _agent_text(turn.relation),
        "check": render_check_prompt(_CONTEXT, _WRITES, profile),
        "source_verify": SOURCE_VERIFY_PROMPT,
        "context_blocks": "\n".join(
            [
                render_alerts_block(["a contredit b"], chronology=chronology),
                render_recent_block([{"name": "A", "entity_type": "t"}]),
                render_user_edits_block([{"kind": "suppression", "detail": "a"}]),
            ]
        ),
        "refusals": "\n".join(
            str(check_add_entity_guards("a", entity_type, set(), profile)[0])
            for entity_type in ("evenement", "etat")
        ),
    }
    if chronology:
        texts["chronicle"] = _agent_text(turn.chronicle)
    if profile is not None:
        texts["schema_hint"] = profile.render_schema_hint()
        texts["relation_refusals"] = "\n".join(
            str(m)
            for m in (
                profile.validate_relation("ZZZ", "a", "b", same_node=False),
                profile.validate_relation(
                    profile.narrative_rel or "ZZZ", "a", "b", same_node=False
                ),
            )
        )
    return texts


@prompt_domain_neutrality_suite.test()
def test_no_fiction_vocabulary_outside_scenario() -> None:
    """Every choice but `scenario` renders zero stoplist word, in any pass."""
    offenders = []
    for key, choice in ATELIER_CHOICES.items():
        if key == "scenario":
            continue
        for pass_name, text in rendered_prompts(choice).items():
            words = sorted({m.lower() for m in STOPLIST.findall(text)})
            if words:
                offenders.append(f"{key}/{pass_name}: {words}")
    assert not offenders, f"fiction vocabulary in non-scenario prompts: {offenders}"


@prompt_domain_neutrality_suite.test()
def test_scenario_keeps_its_rules() -> None:
    """The fiction content moved, it was not lost: scenario still renders the
    death/flash-back checker rules and its narrative verb example."""
    texts = rendered_prompts(ATELIER_CHOICES["scenario"])
    check = texts["check"]
    assert "vivant ET mort" in check
    assert "flash-back" in check
    assert "SUJET PASSIF" in check
    assert "CHRONOLOGIE" in check
    assert "était la maîtresse de" in texts["atelier"]
    assert "chronicle" in texts


@prompt_domain_neutrality_suite.test()
def test_event_checks_only_with_events() -> None:
    """The temporal block of the checker needs a chronology: absent without it."""
    assert SCENARIO_PROFILE.manages_events
    assert not MAINTENANCE_PROFILE.manages_events
    check = render_check_prompt(_CONTEXT, _WRITES, MAINTENANCE_PROFILE)
    assert "CHRONOLOGIE" not in check
    assert "SUPÉRIEUR" not in check
    bare = render_check_prompt(_CONTEXT, _WRITES, None)
    assert "CHRONOLOGIE" not in bare
    # Generic examples stay for everyone.
    for text in (check, bare):
        assert "valeurs qui s'excluent pour une même propriété" in text
        assert "une interdiction ou une règle explicite" in text
        assert "impossibilité spatiale" in text


@prompt_domain_neutrality_suite.test()
def test_documentation_profiles_declare_the_modes_non_contradiction() -> None:
    """The false positive of 2026-09-25 (a document describes several modes and
    says which one is used) is rendered as a NON-contradiction for both
    documentation profiles, in the « différent n'est PAS incompatible » part."""
    for profile in (MAINTENANCE_PROFILE, EMERGENT_SEED_PROFILE):
        check = render_check_prompt(_CONTEXT, _WRITES, profile)
        tail = check[check.index("« différent » n'est PAS « incompatible »") :]
        assert "plusieurs modes" in tail, profile.name
        assert "Ne sont PAS non plus des contradictions" in tail


@prompt_domain_neutrality_suite.test()
def test_no_non_contradiction_section_when_nothing_to_say() -> None:
    """A profile without events nor declared non-contradictions keeps the
    checker prompt free of an empty section."""
    bare = render_check_prompt(_CONTEXT, _WRITES, None)
    assert "Ne sont PAS non plus des contradictions" not in bare
