"""Typage des relations par profil (Option 2) — règles de vocab dur + domaine/portée.

Test déterministe (ni LLM ni Neo4j) de ``Profile.validate_relation`` : la fonction
pure qui décide si une relation est acceptable. Retour : ``None`` = OK,
``str`` = message guidant (refus, renvoyé tel quel à l'agent par add_relation).

Les cas REJET reproduisent les bugs relationnels du run « Alger 1957 » ; les cas OK
verrouillent les relations légitimes ; les cas TOLÉRANCE garantissent qu'on ne
sur-rejette pas un type inconnu (schemaless oblige).
"""
from __future__ import annotations

from protest import ProTestSuite

from felix.core.profile import CHANTIER_PROFILE, SCENARIO_PROFILE

relation_typing_suite = ProTestSuite("RelationTyping")

P = SCENARIO_PROFILE


# ─────────────────────────── REJETS (les bugs d'Alger) ───────────────────────────
@relation_typing_suite.test()
def test_self_loop_rejected() -> None:
    """tract PART_OF tract — une entité ne fait pas partie d'elle-même (règle self-loop)."""
    assert P.validate_relation("PART_OF", "objet", "objet", same_node=True)


@relation_typing_suite.test()
def test_located_at_object_must_be_place() -> None:
    """M. Laurent LOCATED_AT registre — la cible de LOCATED_AT doit être un lieu."""
    assert P.validate_relation("LOCATED_AT", "personnage", "objet", same_node=False)


@relation_typing_suite.test()
def test_targets_object_rejected() -> None:
    """M. Laurent TARGETS tract — on vise un personnage/groupe, pas un objet."""
    assert P.validate_relation("TARGETS", "personnage", "objet", same_node=False)


@relation_typing_suite.test()
def test_witnesses_place_rejected() -> None:
    """M. Dubois WITNESSES école — on témoigne d'un objet/événement, pas d'un lieu."""
    assert P.validate_relation("WITNESSES", "personnage", "lieu", same_node=False)


@relation_typing_suite.test()
def test_member_of_must_be_group() -> None:
    """MEMBER_OF doit pointer vers un groupe/orga, pas vers un personnage."""
    assert P.validate_relation("MEMBER_OF", "personnage", "personnage", same_node=False)


@relation_typing_suite.test()
def test_out_of_vocab_rejected() -> None:
    """INTERROGATES n'est pas dans le vocabulaire du profil — refus."""
    assert P.validate_relation("INTERROGATES", "personnage", "personnage", same_node=False)


# ─────────────────────────── OK (relations légitimes) ───────────────────────────
@relation_typing_suite.test()
def test_owns_object_ok() -> None:
    assert P.validate_relation("OWNS", "personnage", "objet", same_node=False) is None


@relation_typing_suite.test()
def test_located_at_place_ok() -> None:
    assert P.validate_relation("LOCATED_AT", "personnage", "lieu", same_node=False) is None


@relation_typing_suite.test()
def test_knows_ok() -> None:
    assert P.validate_relation("KNOWS", "personnage", "personnage", same_node=False) is None


@relation_typing_suite.test()
def test_targets_person_ok() -> None:
    assert P.validate_relation("TARGETS", "personnage", "personnage", same_node=False) is None


# ─────────────────────────── TOLÉRANCE (pas de sur-rejet) ───────────────────────────
@relation_typing_suite.test()
def test_unknown_type_tolerated() -> None:
    """« langue » n'est pas un type du domaine → on tolère (on ne rejette que les
    violations CLAIRES). Évite les faux rejets sur les types inventés par le modèle."""
    assert P.validate_relation("LOCATED_AT", "personnage", "langue", same_node=False) is None


@relation_typing_suite.test()
def test_profile_without_vocab_allows_everything() -> None:
    """Un profil sans relation_vocabulary (chantier) ne contraint rien — rétrocompat."""
    assert CHANTIER_PROFILE.validate_relation("WHATEVER", "outil", "ouvrage", same_node=False) is None
    assert CHANTIER_PROFILE.validate_relation("ANY", "x", "x", same_node=True) is None
