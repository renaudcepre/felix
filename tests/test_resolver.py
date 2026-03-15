from __future__ import annotations

from felix.ingest.resolver import (
    AmbiguousMatch,
    ResolvedEntity,
    _normalize,
    fuzzy_match_entity,
    slugify,
)

EXISTING = {
    "marie-dupont": "Marie Dupont",
    "pierre-renard": "Pierre Renard",
    "sarah-cohen": "Sarah Cohen",
}

ALIASES = {
    "marie-dupont": ["La Louve"],
    "pierre-renard": ["Le Professeur"],
    "sarah-cohen": ["Docteur Simon"],
}


def test_slugify_basic() -> None:
    assert slugify("Marie Dupont") == "marie-dupont"


def test_slugify_accents() -> None:
    assert slugify("Benoit Laforge") == "benoit-laforge"
    assert slugify("Rene Levesque") == "rene-levesque"


def test_slugify_special_chars() -> None:
    assert slugify("L'inspecteur Benoit") == "l-inspecteur-benoit"


def test_normalize_strips_accents() -> None:
    assert _normalize("Rene") == "rene"
    assert _normalize("Benoit") == "benoit"


def test_exact_match() -> None:
    result = fuzzy_match_entity("Marie Dupont", EXISTING, ALIASES)
    assert isinstance(result, ResolvedEntity)
    assert result.id == "marie-dupont"
    assert result.is_new is False


def test_exact_match_case_insensitive() -> None:
    result = fuzzy_match_entity("marie dupont", EXISTING, ALIASES)
    assert isinstance(result, ResolvedEntity)
    assert result.id == "marie-dupont"


def test_alias_match() -> None:
    result = fuzzy_match_entity("La Louve", EXISTING, ALIASES)
    assert isinstance(result, ResolvedEntity)
    assert result.id == "marie-dupont"


def test_alias_match_docteur_simon() -> None:
    result = fuzzy_match_entity("Docteur Simon", EXISTING, ALIASES)
    assert isinstance(result, ResolvedEntity)
    assert result.id == "sarah-cohen"


def test_no_match_creates_new() -> None:
    result = fuzzy_match_entity("Napoleon Bonaparte", EXISTING, ALIASES)
    assert isinstance(result, ResolvedEntity)
    assert result.is_new is True
    assert result.id == "napoleon-bonaparte"


def test_fuzzy_partial_match() -> None:
    result = fuzzy_match_entity("Marie Dupon", EXISTING, ALIASES)
    # High similarity — either resolved or ambiguous depending on exact ratio
    assert isinstance(result, ResolvedEntity | AmbiguousMatch)
    if isinstance(result, ResolvedEntity):
        assert result.id == "marie-dupont"
    else:
        assert result.best_id == "marie-dupont"


def test_ambiguous_match() -> None:
    # Create entities with similar names
    similar = {
        "jean-dupont": "Jean Dupont",
        "jean-dumont": "Jean Dumont",
    }
    result = fuzzy_match_entity("Jean Dupond", similar)
    # Should match one of the Jeans
    assert isinstance(result, ResolvedEntity | AmbiguousMatch)
    if isinstance(result, AmbiguousMatch):
        assert result.best_id in ("jean-dupont", "jean-dumont")
        assert len(result.candidates) >= 1


def test_no_aliases_param() -> None:
    result = fuzzy_match_entity("Marie Dupont", EXISTING)
    assert isinstance(result, ResolvedEntity)
    assert result.id == "marie-dupont"


def test_different_first_name_same_surname_creates_new() -> None:
    """Elias Milton != Jakes Milton — same surname, different person."""
    family = {"jakes-milton": "Jakes Milton"}
    result = fuzzy_match_entity("Elias Milton", family)
    assert isinstance(result, ResolvedEntity)
    assert result.is_new is True
    assert result.id == "elias-milton"


def test_different_first_name_andrew_milton() -> None:
    """Andrew Milton != Jakes Milton — same surname, different person."""
    family = {"jakes-milton": "Jakes Milton"}
    result = fuzzy_match_entity("Andrew Milton", family)
    assert isinstance(result, ResolvedEntity)
    assert result.is_new is True
    assert result.id == "andrew-milton"


def test_shared_word_triggers_ambiguous() -> None:
    """'Vaisseau spatial' should match 'Vaisseau Elysium-7' (shared word 'vaisseau')."""
    locs = {"vaisseau-elysium-7": "Vaisseau Elysium-7"}
    result = fuzzy_match_entity("Vaisseau spatial", locs)
    assert isinstance(result, AmbiguousMatch)
    assert result.best_id == "vaisseau-elysium-7"


def test_token_inversion_match() -> None:
    """'Martin Jean' doit matcher 'Jean Martin' (même personne, ordre inversé)."""
    chars = {"jean-martin": "Jean Martin"}
    result = fuzzy_match_entity("Martin Jean", chars)
    assert isinstance(result, ResolvedEntity)
    assert result.id == "jean-martin"


def test_single_token_does_not_auto_resolve() -> None:
    """'Voss' seul ne doit pas auto-resolver vers 'Lena Voss' (score penalise -> AmbiguousMatch)."""
    chars = {"lena-voss": "Lena Voss"}
    result = fuzzy_match_entity("Voss", chars)
    assert isinstance(result, AmbiguousMatch)
    assert result.best_id == "lena-voss"


def test_single_token_ambiguous_two_candidates() -> None:
    """'Voss' avec deux personnages Voss -> AmbiguousMatch avec les deux candidats."""
    chars = {"lena-voss": "Lena Voss", "karl-voss": "Karl Voss"}
    result = fuzzy_match_entity("Voss", chars)
    assert isinstance(result, AmbiguousMatch)
    assert len(result.candidates) == 2  # noqa: PLR2004


def test_no_shared_word_skips() -> None:
    """'Naomi Chen' should NOT match 'Lucas Terra' (no shared word)."""
    chars = {"biologiste-lucas-terra": "Biologiste Lucas Terra"}
    result = fuzzy_match_entity("Exobiologiste Naomi Chen", chars)
    assert isinstance(result, ResolvedEntity)
    assert result.is_new is True
