"""Profil ÉMERGENT (Étapes 1, 2, 6 du plan `maintenance_profile.md`) — vocabulaire
fermé quand un canal narratif existe, seed nu, et sélection évolutive.

Univers de TEST des cas synthétiques : presse à balles BX-9 (cf.
[[feedback_prompt_test_leakage]], déjà utilisé par test_schema_changes.py).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from protest import ProTestSuite, Use, fixture

import felix.atelier.agent as atelier_agent_module
from felix.atelier.agent import (
    ATELIER_CHOICES,
    build_gate_agent,
    build_master_agent,
    build_turn_agents,
    profile_summary,
    resolve_profile,
)
from felix.core.graph import NARRATIVE_REL
from felix.core.profile import (
    CHANTIER_PROFILE,
    EMERGENT_SEED_PROFILE,
    EntityType,
    Profile,
    RelationSpec,
)
from felix.core.profile_store import save_project_profile
from felix.graph.driver import get_driver, setup_constraints

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from neo4j import AsyncDriver

emergent_profile_suite = ProTestSuite("EmergentProfile")

PROJ = "test-emergent-profile"


async def _wipe(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MATCH (n:ProjectProfile {project: $p}) DETACH DELETE n", p=PROJ,
        )


@fixture(max_concurrency=1)
async def _driver() -> AsyncGenerator[AsyncDriver]:
    driver = get_driver()
    await setup_constraints(driver)
    try:
        yield driver
    finally:
        await _wipe(driver)
        await driver.close()


# ──────────────────── Étape 1 — vocabulaire fermé ────────────────────

@emergent_profile_suite.test()
def test_narrative_rel_with_empty_vocab_refuses_structural_type() -> None:
    """Un profil avec narrative_rel ET vocab VIDE refuse tout type hors LIE_A —
    avant ce fix, vocab vide = tout permis (trou de vocab, cf. plan étape 1)."""
    msg = EMERGENT_SEED_PROFILE.validate_relation(
        "CONTROLS", "organe", "organe", same_node=False
    )
    assert msg is not None
    assert NARRATIVE_REL in msg


@emergent_profile_suite.test()
def test_narrative_rel_with_empty_vocab_still_accepts_narrative_channel() -> None:
    """Le canal narratif lui-même reste ouvert (verbe verbatim requis)."""
    msg = EMERGENT_SEED_PROFILE.validate_relation(
        NARRATIVE_REL, "organe", "organe", same_node=False, verbe="règle"
    )
    assert msg is None


@emergent_profile_suite.test()
def test_narrative_rel_with_empty_vocab_refusal_guides_to_lie_a() -> None:
    """Le message de refus pointe explicitement vers LIE_A + verbe verbatim."""
    msg = EMERGENT_SEED_PROFILE.validate_relation(
        "PILOTE", "organe", "organe", same_node=False
    )
    assert msg is not None
    assert "verbe" in msg.lower()


@emergent_profile_suite.test()
def test_chantier_profile_unchanged_empty_vocab_no_narrative_rel() -> None:
    """CHANTIER (pas de narrative_rel, vocab vide) reste PERMISSIF — non-régression
    explicite de la condition touchée."""
    assert CHANTIER_PROFILE.narrative_rel == ""
    assert not CHANTIER_PROFILE.relation_vocabulary
    assert CHANTIER_PROFILE.validate_relation(
        "ANYTHING", "outil", "materiau", same_node=False
    ) is None


@emergent_profile_suite.test()
def test_profile_without_narrative_rel_and_empty_vocab_stays_permissive() -> None:
    """Cas générique (pas seulement chantier) : sans narrative_rel, vocab vide ⇒
    tout permis, comme avant le fix."""
    bare = Profile(name="nu", description="", entity_types=())
    assert bare.validate_relation("ANYTHING", "x", "y", same_node=False) is None


@emergent_profile_suite.test()
def test_populated_vocab_with_narrative_rel_behavior_unchanged() -> None:
    """Un profil à vocab NON vide + narrative_rel (ex. maintenance) garde son
    comportement d'avant : le refus liste les types structurels exacts."""
    profile = Profile(
        name="test", description="", entity_types=(),
        relation_vocabulary=(RelationSpec("CONTROLS", "pilote"),),
        narrative_rel=NARRATIVE_REL,
    )
    msg = profile.validate_relation("MONITORS", "a", "b", same_node=False)
    assert msg is not None
    assert "CONTROLS" in msg
    assert NARRATIVE_REL in msg


# ──────────────────── Étape 2 — EMERGENT_SEED_PROFILE ────────────────────

@emergent_profile_suite.test()
def test_seed_profile_has_no_entity_types() -> None:
    assert EMERGENT_SEED_PROFILE.entity_types == ()


@emergent_profile_suite.test()
def test_seed_profile_has_no_relation_vocabulary() -> None:
    assert EMERGENT_SEED_PROFILE.relation_vocabulary == ()


@emergent_profile_suite.test()
def test_seed_profile_opens_narrative_channel() -> None:
    assert EMERGENT_SEED_PROFILE.narrative_rel == NARRATIVE_REL


@emergent_profile_suite.test()
def test_seed_profile_does_not_manage_events() -> None:
    assert EMERGENT_SEED_PROFILE.manages_events is False


@emergent_profile_suite.test()
def test_seed_profile_reserves_described_in_to_code() -> None:
    assert EMERGENT_SEED_PROFILE.code_only_relations == ("DESCRIBED_IN",)


@emergent_profile_suite.test()
def test_seed_profile_has_domain_neutral_modeling_rules() -> None:
    """Pas de vocabulaire de domaine (organe, commande…) dans les règles — le
    seed doit rester neutre, réutilisable pour n'importe quel objet documenté."""
    joined = " ".join(EMERGENT_SEED_PROFILE.modeling_rules).lower()
    assert "verbatim" in joined
    assert "boilerplate" in joined
    for domain_word in ("organe", "commande", "machine", "consigne"):
        assert domain_word not in joined


@emergent_profile_suite.test()
def test_seed_profile_has_generic_consistency_rules() -> None:
    assert EMERGENT_SEED_PROFILE.consistency_rules


# ──────────────────── Étape 6 — choix évolutif + resolve_profile ────────────────────

@emergent_profile_suite.test()
def test_agent_choice_defaults_to_non_evolving() -> None:
    assert ATELIER_CHOICES["scenario"].evolving is False
    assert ATELIER_CHOICES["maintenance"].evolving is False


@emergent_profile_suite.test()
def test_emergent_choice_is_evolving_with_seed_profile() -> None:
    choice = ATELIER_CHOICES["emergent"]
    assert choice.evolving is True
    assert choice.profile is EMERGENT_SEED_PROFILE


@emergent_profile_suite.test()
def test_emergent_choice_reuses_maintenance_personas() -> None:
    """Le plan demande les personas/prompts maintenance pour l'émergent (assistant
    documentaire factuel — la posture qui convient à un domaine inconnu)."""
    emergent = ATELIER_CHOICES["emergent"]
    maintenance = ATELIER_CHOICES["maintenance"]
    assert emergent.persona == maintenance.persona
    assert emergent.master_prompt == maintenance.master_prompt
    assert emergent.gate_prompt == maintenance.gate_prompt
    assert emergent.master_persona == maintenance.master_persona


@emergent_profile_suite.test()
async def test_resolve_profile_non_evolving_ignores_db_and_returns_choice_profile() -> None:
    choice = ATELIER_CHOICES["scenario"]
    # driver=None : un choix non-évolutif ne doit JAMAIS toucher la base.
    profile = await resolve_profile(None, choice, project="whatever")  # type: ignore[arg-type]
    assert profile is choice.profile


@emergent_profile_suite.test()
async def test_resolve_profile_evolving_without_stored_falls_back_to_seed(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    choice = ATELIER_CHOICES["emergent"]
    profile = await resolve_profile(driver, choice, project=PROJ)
    assert profile is EMERGENT_SEED_PROFILE


@emergent_profile_suite.test()
async def test_resolve_profile_evolving_with_stored_returns_stored(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    await _wipe(driver)
    evolved = Profile(
        name="documentation technique", description="évolué",
        entity_types=(), narrative_rel=NARRATIVE_REL,
        relation_vocabulary=(RelationSpec("CONTROLS", "pilote"),),
    )
    await save_project_profile(driver, evolved, project=PROJ)

    choice = ATELIER_CHOICES["emergent"]
    profile = await resolve_profile(driver, choice, project=PROJ)
    assert profile == evolved
    assert profile is not EMERGENT_SEED_PROFILE


# ──────────────────── vocabulaire UI (GET /api/atelier/profiles, Étape 8) ────────────────────
# Plus AUCUN texte scénario codé en dur côté front : welcome/input_placeholder
# viennent du mode choisi (cf. felix.atelier.agent.profile_summary).

@emergent_profile_suite.test()
def test_all_choices_have_non_empty_ui_vocabulary() -> None:
    for choice in ATELIER_CHOICES.values():
        assert choice.welcome.strip(), f"{choice.key} : welcome vide"
        assert choice.input_placeholder.strip(), f"{choice.key} : input_placeholder vide"


@emergent_profile_suite.test()
def test_scenario_keeps_its_fiction_wording() -> None:
    """Le mode scénario garde sa voix « histoire »/« bible » — c'est le seul mode
    où ce vocabulaire est légitime (il vient du CHOIX, pas d'une constante unique
    imposée à tous les modes)."""
    scenario = ATELIER_CHOICES["scenario"]
    assert "histoire" in scenario.welcome.lower()
    assert "bible" in scenario.welcome.lower()


@emergent_profile_suite.test()
def test_emergent_and_maintenance_share_documentary_wording() -> None:
    """Même posture d'assistant documentaire (cf. personas partagées ci-dessus) →
    même invite, ni « histoire » ni « personnage »."""
    emergent = ATELIER_CHOICES["emergent"]
    maintenance = ATELIER_CHOICES["maintenance"]
    assert emergent.welcome == maintenance.welcome
    assert "documentation" in emergent.welcome.lower()
    for fiction_word in ("histoire", "personnage", "bible", "scénario"):
        assert fiction_word not in emergent.welcome.lower()
        assert fiction_word not in emergent.input_placeholder.lower()


@emergent_profile_suite.test()
def test_profile_summary_keeps_key_and_label() -> None:
    summary = profile_summary(ATELIER_CHOICES["scenario"])
    assert summary["key"] == "scenario"
    assert summary["label"] == "Scénario"


@emergent_profile_suite.test()
def test_profile_summary_exposes_ui_vocabulary_and_evolving() -> None:
    summary = profile_summary(ATELIER_CHOICES["emergent"])
    assert summary["welcome"] == ATELIER_CHOICES["emergent"].welcome
    assert summary["input_placeholder"] == ATELIER_CHOICES["emergent"].input_placeholder
    assert summary["evolving"] is True


# ──────────────────── #82 — build_turn_agents ────────────────────
# Avant ce fix, un choix ÉVOLUTIF ne reconstruisait pour le profil résolu que
# ses 3 agents extracteurs (cf. route) : le maître et le gate restaient sur les
# dicts pré-construits d'app.state, donc sur le SEED — le chat ne connaissait
# jamais le vocabulaire appris (#82).

def _instructions_text(agent: object) -> str:
    """Instructions concaténées d'un Agent pydantic-ai — inspection SANS appel
    réseau. Tous nos builders passent ``instructions=`` comme une simple
    chaîne (jamais une fonction dynamique), donc ``agent._instructions`` est
    une liste à un seul élément ici."""
    return "".join(agent._instructions)  # type: ignore[attr-defined]


_EVOLVED_WITH_PROMOTED_TYPE = Profile(
    name="documentation technique", description="évolué",
    entity_types=(EntityType("vanne", ("emplacement",)),),
    narrative_rel=NARRATIVE_REL,
    relation_vocabulary=(RelationSpec("CONTROLS", "pilote"),),
)


@emergent_profile_suite.test()
async def test_build_turn_agents_master_and_gate_learn_promoted_type(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Un profil ÉVOLUÉ stocké (type promu 'vanne') apparaît dans les
    instructions du MAÎTRE et du GATE — pas seulement des extracteurs (#82)."""
    await _wipe(driver)
    await save_project_profile(driver, _EVOLVED_WITH_PROMOTED_TYPE, project=PROJ)

    choice = ATELIER_CHOICES["emergent"]
    profile = await resolve_profile(driver, choice, project=PROJ)
    turn = build_turn_agents(choice, profile)

    assert "vanne" in _instructions_text(turn.master)
    assert "vanne" in _instructions_text(turn.gate)


@emergent_profile_suite.test()
async def test_build_turn_agents_extractors_also_learn_promoted_type(
    driver: Annotated[AsyncDriver, Use(_driver)],
) -> None:
    """Non-régression : les 3 extracteurs restent bâtis sur le même profil
    résolu (déjà vrai avant #82 — la route les reconstruisait déjà)."""
    await _wipe(driver)
    await save_project_profile(driver, _EVOLVED_WITH_PROMOTED_TYPE, project=PROJ)

    choice = ATELIER_CHOICES["emergent"]
    profile = await resolve_profile(driver, choice, project=PROJ)
    turn = build_turn_agents(choice, profile)

    assert "vanne" in _instructions_text(turn.atelier)
    assert "vanne" in _instructions_text(turn.relation)
    assert "vanne" in _instructions_text(turn.chronicle)


@emergent_profile_suite.test()
def test_non_evolving_gate_agent_keeps_bare_gate_prompt() -> None:
    """Chemin non-évolutif (main.py appelle build_gate_agent(choice) SANS 2e
    argument) : aucun bloc n'est collé — comportement inchangé."""
    choice = ATELIER_CHOICES["scenario"]
    gate = build_gate_agent(choice)
    assert _instructions_text(gate) == choice.gate_prompt


@emergent_profile_suite.test()
def test_non_evolving_master_agent_uses_choice_profile_by_default() -> None:
    """Sans override, build_master_agent retombe sur choice.profile — identique
    à avant #82 pour un choix non évolutif."""
    choice = ATELIER_CHOICES["scenario"]
    default_master = build_master_agent(choice)
    explicit_master = build_master_agent(choice, profile=choice.profile)
    assert _instructions_text(default_master) == _instructions_text(explicit_master)


@emergent_profile_suite.test()
def test_gate_agent_appends_short_profile_block_with_types_and_relations() -> None:
    profile = Profile(
        name="test", description="", entity_types=(EntityType("vanne", ()),),
        relation_vocabulary=(RelationSpec("CONTROLS", "pilote"),),
    )
    choice = ATELIER_CHOICES["emergent"]
    gate = build_gate_agent(choice, profile)
    joined = _instructions_text(gate)
    assert "vanne" in joined
    assert "CONTROLS" in joined


@emergent_profile_suite.test()
def test_gate_agent_skips_block_when_profile_has_no_vocabulary_yet() -> None:
    """Le seed émergent tout neuf (aucun type/relation encore appris) ne colle
    RIEN au gate — reste cheap tant qu'il n'y a rien à apprendre."""
    choice = ATELIER_CHOICES["emergent"]
    gate = build_gate_agent(choice, EMERGENT_SEED_PROFILE)
    assert _instructions_text(gate) == choice.gate_prompt


@emergent_profile_suite.test()
def test_gate_profile_block_has_no_modeling_rules_dump() -> None:
    """Le bloc gate ne colle QUE des noms — pas modeling_rules ni examples
    (garder le gate cheap, #82)."""
    profile = Profile(
        name="test", description="", entity_types=(EntityType("vanne", ()),),
        modeling_rules=("une règle qui ne doit PAS fuiter dans le gate",),
        relation_vocabulary=(
            RelationSpec("CONTROLS", "pilote", examples="ne doit pas fuiter non plus"),
        ),
    )
    block = profile.render_gate_block()
    assert "vanne" in block
    assert "CONTROLS" in block
    assert "ne doit PAS fuiter" not in block
    assert "ne doit pas fuiter non plus" not in block


@emergent_profile_suite.test()
def test_build_turn_agents_does_not_read_the_db_itself() -> None:
    """build_turn_agents prend un profil DÉJÀ résolu : elle ne doit JAMAIS
    relire la base elle-même — sinon on retombe sur un double appel
    resolve_profile/tour (#82 : un seul, côté route)."""
    calls: list[str] = []
    original = atelier_agent_module.load_project_profile

    async def spy(driver: AsyncDriver, *, project: str) -> Profile | None:
        calls.append(project)
        return await original(driver, project=project)

    atelier_agent_module.load_project_profile = spy
    try:
        choice = ATELIER_CHOICES["emergent"]
        build_turn_agents(choice, EMERGENT_SEED_PROFILE)
    finally:
        atelier_agent_module.load_project_profile = original
    assert calls == []


@emergent_profile_suite.test()
def test_profile_summary_non_evolving_choice_reports_false() -> None:
    assert profile_summary(ATELIER_CHOICES["scenario"])["evolving"] is False
