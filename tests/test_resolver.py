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
