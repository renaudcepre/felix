from __future__ import annotations

from protest import ProTestSuite

from felix.ingest.resolver import (
    AmbiguousMatch,
    ResolvedEntity,
    fuzzy_match_entity,
    slugify,
)
from felix.ingest.utils import normalize

resolver_suite = ProTestSuite("Resolver")

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


@resolver_suite.test()
def test_slugify_basic() -> None:
    assert slugify("Marie Dupont") == "marie-dupont"


@resolver_suite.test()
def test_slugify_accents() -> None:
    assert slugify("Benoit Laforge") == "benoit-laforge"
    assert slugify("Rene Levesque") == "rene-levesque"


@resolver_suite.test()
def test_slugify_special_chars() -> None:
    # Apostrophe MILIEU de phrase (pas un article de tête) → tiret, conservée.
    assert slugify("Cartel d'Ophir") == "cartel-d-ophir"


# ─────── Article de tête retiré → « le pêcheur » et « pêcheur » = même id (anti-doublon) ───────
# Le doublon à l'article près (« le pêcheur »/« pêcheur », « l'équipe »/« équipe ») a persisté
# sur Haiku ET Sonnet → c'est structurel (model-independent), réglé dans slugify : retirer
# l'article de tête (le/la/les/l'/un/une/des) aligne l'id → fusion dès add_entity (MERGE sur id).
@resolver_suite.test()
def test_slugify_strips_leading_article() -> None:
    assert slugify("le pêcheur") == slugify("pêcheur") == "pecheur"
    assert slugify("les Sentinelles") == slugify("Sentinelles") == "sentinelles"
    assert slugify("l'équipe de Castan") == slugify("équipe de Castan") == "equipe-de-castan"
    assert slugify("une balise") == slugify("balise") == "balise"


@resolver_suite.test()
def test_slugify_strips_curly_apostrophe_article() -> None:
    # Les LLM produisent souvent l'apostrophe typographique « ’ » — à traiter comme « ' ».
    assert slugify("l’Aurore Pâle") == slugify("Aurore Pâle") == "aurore-pale"


@resolver_suite.test()
def test_slugify_keeps_non_article_words() -> None:
    # Un mot qui COMMENCE par les lettres d'un article n'est pas un article (pas d'espace après).
    assert slugify("lapin") == "lapin"        # pas « la » + reste
    assert slugify("larme") == "larme"        # pas « l' » (aucune apostrophe)
    assert slugify("Léviathan") == "leviathan"
    # « de » au milieu n'est pas un article de tête → conservé.
    assert slugify("sabre de Korr") == "sabre-de-korr"


@resolver_suite.test()
def test_slugify_article_only_name_not_emptied() -> None:
    # Un nom réduit au seul article ne doit jamais devenir vide.
    assert slugify("Le") == "le"
    assert slugify("Les") == "les"


@resolver_suite.test()
def test_normalize_strips_accents() -> None:
    assert normalize("Rene") == "rene"
    assert normalize("Benoit") == "benoit"


@resolver_suite.test()
def test_exact_match() -> None:
    result = fuzzy_match_entity("Marie Dupont", EXISTING, ALIASES)
    assert isinstance(result, ResolvedEntity)
    assert result.id == "marie-dupont"
    assert result.is_new is False


@resolver_suite.test()
def test_exact_match_case_insensitive() -> None:
    result = fuzzy_match_entity("marie dupont", EXISTING, ALIASES)
    assert isinstance(result, ResolvedEntity)
    assert result.id == "marie-dupont"


@resolver_suite.test()
def test_alias_match() -> None:
    result = fuzzy_match_entity("La Louve", EXISTING, ALIASES)
    assert isinstance(result, ResolvedEntity)
    assert result.id == "marie-dupont"


@resolver_suite.test()
def test_alias_match_docteur_simon() -> None:
    result = fuzzy_match_entity("Docteur Simon", EXISTING, ALIASES)
    assert isinstance(result, ResolvedEntity)
    assert result.id == "sarah-cohen"


@resolver_suite.test()
def test_no_match_creates_new() -> None:
    result = fuzzy_match_entity("Napoleon Bonaparte", EXISTING, ALIASES)
    assert isinstance(result, ResolvedEntity)
    assert result.is_new is True
    assert result.id == "napoleon-bonaparte"


@resolver_suite.test()
def test_fuzzy_partial_match() -> None:
    result = fuzzy_match_entity("Marie Dupon", EXISTING, ALIASES)
    # High similarity — either resolved or ambiguous depending on exact ratio
    assert isinstance(result, ResolvedEntity | AmbiguousMatch)
    if isinstance(result, ResolvedEntity):
        assert result.id == "marie-dupont"
    else:
        assert result.best_id == "marie-dupont"


@resolver_suite.test()
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


@resolver_suite.test()
def test_no_aliases_param() -> None:
    result = fuzzy_match_entity("Marie Dupont", EXISTING)
    assert isinstance(result, ResolvedEntity)
    assert result.id == "marie-dupont"


@resolver_suite.test()
def test_different_first_name_same_surname_creates_new() -> None:
    """Elias Milton != Jakes Milton — same surname, different person."""
    family = {"jakes-milton": "Jakes Milton"}
    result = fuzzy_match_entity("Elias Milton", family)
    assert isinstance(result, ResolvedEntity)
    assert result.is_new is True
    assert result.id == "elias-milton"


@resolver_suite.test()
def test_different_first_name_andrew_milton() -> None:
    """Andrew Milton != Jakes Milton — same surname, different person."""
    family = {"jakes-milton": "Jakes Milton"}
    result = fuzzy_match_entity("Andrew Milton", family)
    assert isinstance(result, ResolvedEntity)
    assert result.is_new is True
    assert result.id == "andrew-milton"


@resolver_suite.test()
def test_shared_word_triggers_ambiguous() -> None:
    """'Vaisseau spatial' should match 'Vaisseau Elysium-7' (shared word 'vaisseau')."""
    locs = {"vaisseau-elysium-7": "Vaisseau Elysium-7"}
    result = fuzzy_match_entity("Vaisseau spatial", locs)
    assert isinstance(result, AmbiguousMatch)
    assert result.best_id == "vaisseau-elysium-7"


@resolver_suite.test()
def test_token_inversion_match() -> None:
    """'Martin Jean' doit matcher 'Jean Martin' (meme personne, ordre inverse)."""
    chars = {"jean-martin": "Jean Martin"}
    result = fuzzy_match_entity("Martin Jean", chars)
    assert isinstance(result, ResolvedEntity)
    assert result.id == "jean-martin"


@resolver_suite.test()
def test_single_token_does_not_auto_resolve() -> None:
    """'Voss' seul ne doit pas auto-resolver vers 'Lena Voss' (score penalise -> AmbiguousMatch)."""
    chars = {"lena-voss": "Lena Voss"}
    result = fuzzy_match_entity("Voss", chars)
    assert isinstance(result, AmbiguousMatch)
    assert result.best_id == "lena-voss"


@resolver_suite.test()
def test_single_token_ambiguous_two_candidates() -> None:
    """'Voss' avec deux personnages Voss -> AmbiguousMatch avec les deux candidats."""
    chars = {"lena-voss": "Lena Voss", "karl-voss": "Karl Voss"}
    result = fuzzy_match_entity("Voss", chars)
    assert isinstance(result, AmbiguousMatch)
    assert len(result.candidates) == 2  # noqa: PLR2004


@resolver_suite.test()
def test_no_shared_word_skips() -> None:
    """'Naomi Chen' should NOT match 'Lucas Terra' (no shared word)."""
    chars = {"biologiste-lucas-terra": "Biologiste Lucas Terra"}
    result = fuzzy_match_entity("Exobiologiste Naomi Chen", chars)
    assert isinstance(result, ResolvedEntity)
    assert result.is_new is True
