"""Typage des relations par profil (#68) — noyau structurel dur + canal narratif.

Test déterministe (ni LLM ni Neo4j) de ``Profile.validate_relation`` : la fonction
pure qui décide si une relation est acceptable. Retour : ``None`` = OK,
``str`` = message guidant (refus, renvoyé tel quel à l'agent par add_relation).

Trois familles :
- STRUCTUREL : le vocab dur conservé (LOCATED_AT/MEMBER_OF/PART_OF) garde sa
  validation domaine/portée — les cas REJET reproduisent les bugs d'« Alger 1957 » ;
- NARRATIF : LIE_A exige un verbe verbatim, n'a AUCUNE validation domaine/portée
  (zéro trou par construction), et le hors-vocab est REDIRIGÉ vers lui — les
  anciens types narratifs (LOVES…) ne sont plus du vocab ;
- TOLÉRANCE : pas de sur-rejet d'un type d'entité inconnu (schemaless), et un
  profil sans vocab ni canal narratif ne contraint rien.
"""
from __future__ import annotations

from protest import ProTestSuite

from felix.core.graph import NARRATIVE_REL
from felix.core.profile import CHANTIER_PROFILE, SCENARIO_PROFILE

relation_typing_suite = ProTestSuite("RelationTyping")

P = SCENARIO_PROFILE


# ──────────────────── STRUCTUREL : rejets (les bugs d'Alger) ────────────────────
@relation_typing_suite.test()
def test_self_loop_rejected() -> None:
    """tract PART_OF tract — une entité ne fait pas partie d'elle-même (règle self-loop)."""
    assert P.validate_relation("PART_OF", "objet", "objet", same_node=True)


@relation_typing_suite.test()
def test_located_at_object_must_be_place() -> None:
    """M. Laurent LOCATED_AT registre — la cible de LOCATED_AT doit être un lieu."""
    assert P.validate_relation("LOCATED_AT", "personnage", "objet", same_node=False)


@relation_typing_suite.test()
def test_member_of_must_be_group() -> None:
    """MEMBER_OF doit pointer vers un groupe/orga, pas vers un personnage."""
    assert P.validate_relation("MEMBER_OF", "personnage", "personnage", same_node=False)


# ──────────────────── STRUCTUREL : relations légitimes ────────────────────
@relation_typing_suite.test()
def test_located_at_place_ok() -> None:
    assert P.validate_relation("LOCATED_AT", "personnage", "lieu", same_node=False) is None


@relation_typing_suite.test()
def test_located_at_group_ok() -> None:
    """« il y a des orques à Adator » — un groupe vit/opère quelque part. Trou vu en
    sonde (session Adator) : sujet groupe refusé, reliquat d'AVANT le type groupe
    (ajouté pour MEMBER_OF sans étendre LOCATED_AT)."""
    assert P.validate_relation("LOCATED_AT", "groupe", "lieu", same_node=False) is None


@relation_typing_suite.test()
def test_part_of_place_ok() -> None:
    assert P.validate_relation("PART_OF", "lieu", "lieu", same_node=False) is None


# ──────────────────── NARRATIF : LIE_A {verbe verbatim} (#68) ────────────────────
@relation_typing_suite.test()
def test_narratif_verbe_ok() -> None:
    """Tessa LIE_A {verbe='était la maîtresse de'} Hadrin — le verbe de l'auteur
    EST la donnée, aucun type canonique à choisir."""
    assert P.validate_relation(
        "LIE_A", "personnage", "personnage", same_node=False,
        verbe="était la maîtresse de",
    ) is None


@relation_typing_suite.test()
def test_narratif_sans_domaine_portee() -> None:
    """AUCUNE validation domaine/portée sur le narratif : « le passeur transporte
    les lanternes » (personnage→objet) passe sans qu'un typage l'énumère — zéro
    trou par construction (prix assumé de #68)."""
    assert P.validate_relation(
        "LIE_A", "personnage", "objet", same_node=False, verbe="transporte",
    ) is None


@relation_typing_suite.test()
def test_narratif_verbe_requis() -> None:
    """LIE_A sans verbe = arête muette → refus GUIDANT (le message réclame le verbe)."""
    msg = P.validate_relation("LIE_A", "personnage", "personnage", same_node=False)
    assert msg and "verbe" in msg


@relation_typing_suite.test()
def test_narratif_self_loop_rejected() -> None:
    """Même narratif, pas de boucle a==b (un personnage ne se commande pas lui-même)."""
    assert P.validate_relation(
        "LIE_A", "personnage", "personnage", same_node=True, verbe="commande",
    )


@relation_typing_suite.test()
def test_hors_vocab_redirige_vers_narratif() -> None:
    """INTERROGATES (type inventé) → refus qui REDIRIGE vers le canal narratif :
    plus de trou de vocab, le lien réel a toujours une sortie."""
    msg = P.validate_relation("INTERROGATES", "personnage", "personnage", same_node=False)
    assert msg and NARRATIVE_REL in msg


@relation_typing_suite.test()
def test_ancien_type_narratif_rejete() -> None:
    """LOVES (ex-vocab narratif) n'est PLUS un type du domaine : refus redirigé —
    le verbe verbatim a remplacé la traduction qui ment (« maîtresse » → LOVES)."""
    msg = P.validate_relation("LOVES", "personnage", "personnage", same_node=False)
    assert msg and NARRATIVE_REL in msg


# ──────────────────── TOLÉRANCE (pas de sur-rejet) ────────────────────
@relation_typing_suite.test()
def test_unknown_type_tolerated() -> None:
    """« langue » n'est pas un type du domaine → on tolère (on ne rejette que les
    violations CLAIRES). Évite les faux rejets sur les types inventés par le modèle."""
    assert P.validate_relation("LOCATED_AT", "personnage", "langue", same_node=False) is None


@relation_typing_suite.test()
def test_profile_without_vocab_allows_everything() -> None:
    """Un profil sans relation_vocabulary ni narrative_rel (chantier) ne contraint
    rien — rétrocompat."""
    assert CHANTIER_PROFILE.validate_relation("WHATEVER", "outil", "ouvrage", same_node=False) is None
    assert CHANTIER_PROFILE.validate_relation("ANY", "x", "x", same_node=True) is None
