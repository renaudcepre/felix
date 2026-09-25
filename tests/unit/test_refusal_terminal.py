"""Refus terminal (issue #59) — les gardes sémantiques mémorisent les noms refusés.

Bug : add_entity("bataille", type="evenement") → refus + message listant les types
alternatifs → le modèle retente en type="groupe" → accepté. Chaque garde marche ;
leur composition échoue.

Fix : (1) les messages de refus sont TERMINAUX (plus de liste de types alternatifs) ;
(2) check_add_entity_guards mémorise le slug du nom dans refused_names → toute
re-création du même nom sous un autre type est refusée en code.

Anti-leakage : les noms de ce module (Cendral, Brulvie) ne doivent PAS apparaître
dans les prompts des agents (src/felix/) — vérification dans test_no_test_names_in_prompts.
"""
from __future__ import annotations

import pathlib
import re

from protest import ProTestSuite

from felix.core.profile import SCENARIO_PROFILE
from felix.core.tools import check_add_entity_guards
from felix.ingest.resolver import slugify

refusal_terminal_suite = ProTestSuite("RefusalTerminal")

# Noms dédiés à ces tests — univers isolé (anti-leakage vérifié ci-dessous).
_TEST_NAMES = ("Cendral", "Brulvie")

# Profil scénario : manages_events=True (la garde evenement est active).
_PROF = SCENARIO_PROFILE


# ──────────── 1. Le slug du nom refusé entre dans refused_names ─────────────

@refusal_terminal_suite.test()
def test_evenement_refus_signale_ajout() -> None:
    """check_add_entity_guards(type='evenement') → add_to_refused=True."""
    _msg, add = check_add_entity_guards(
        "la bataille des Cendral", "evenement", set(), _PROF
    )
    assert add is True, "la garde evenement doit signaler l'ajout au refused_names"


@refusal_terminal_suite.test()
def test_evenement_refus_message_non_nul() -> None:
    """check_add_entity_guards(type='evenement') → message de refus non vide."""
    msg, _add = check_add_entity_guards(
        "la bataille des Cendral", "evenement", set(), _PROF
    )
    assert msg is not None


# ──────────── 2. Re-création bloquée (avec et sans article) ─────────────────

@refusal_terminal_suite.test()
def test_retente_avec_article_bloquee() -> None:
    """Après refus, re-création 'la bataille des Cendral' type='groupe' → bloquée."""
    slug = slugify("la bataille des Cendral")
    msg, _add = check_add_entity_guards(
        "la bataille des Cendral", "groupe", {slug}, _PROF
    )
    assert msg is not None, "la re-création avec article doit être refusée"


@refusal_terminal_suite.test()
def test_retente_sans_article_meme_slug() -> None:
    """slugify retire l'article de tête → 'bataille des Cendral' = même slug."""
    assert slugify("la bataille des Cendral") == slugify("bataille des Cendral"), (
        "slugify doit normaliser l'article de tête"
    )


@refusal_terminal_suite.test()
def test_retente_sans_article_bloquee() -> None:
    """Après refus, re-création 'bataille des Cendral' (sans article) → bloquée."""
    slug = slugify("la bataille des Cendral")
    msg, _add = check_add_entity_guards(
        "bataille des Cendral", "groupe", {slug}, _PROF
    )
    assert msg is not None, "la re-création sans article doit être refusée (même slug)"


# ──────────── 3. Même séquence pour la garde anti-état ──────────────────────

@refusal_terminal_suite.test()
def test_maladie_refus_signale_ajout() -> None:
    """check_add_entity_guards(type='maladie') → add_to_refused=True."""
    _msg, add = check_add_entity_guards(
        "la fièvre de Brulvie", "maladie", set(), _PROF
    )
    assert add is True


@refusal_terminal_suite.test()
def test_maladie_refus_message_non_nul() -> None:
    """check_add_entity_guards(type='maladie') → message de refus non vide."""
    msg, _add = check_add_entity_guards(
        "la fièvre de Brulvie", "maladie", set(), _PROF
    )
    assert msg is not None


@refusal_terminal_suite.test()
def test_maladie_retente_objet_bloquee() -> None:
    """Après refus maladie, re-création du même nom type='objet' → bloquée."""
    slug = slugify("la fièvre de Brulvie")
    msg, _add = check_add_entity_guards(
        "la fièvre de Brulvie", "objet", {slug}, _PROF
    )
    assert msg is not None, "la re-création d'un état refusé sous type='objet' doit être bloquée"


# ──────────── 4. Message evenement sans liste de types alternatifs ───────────

@refusal_terminal_suite.test()
def test_message_evenement_sans_personnage() -> None:
    """Le message de refus 'evenement' ne mentionne plus 'personnage' (guide supprimé)."""
    msg, _ = check_add_entity_guards(
        "la bataille des Cendral", "evenement", set(), _PROF
    )
    assert msg is not None
    assert "personnage" not in msg.lower(), (
        "le message ne doit plus lister 'personnage' comme type alternatif"
    )


@refusal_terminal_suite.test()
def test_message_evenement_sans_lieu_ni_objet() -> None:
    """Le message de refus 'evenement' ne mentionne plus 'lieu' ni 'objet'."""
    msg, _ = check_add_entity_guards(
        "la bataille des Cendral", "evenement", set(), _PROF
    )
    assert msg is not None
    assert "lieu" not in msg.lower(), "le message ne doit plus lister 'lieu'"
    assert "objet" not in msg.lower(), "le message ne doit plus lister 'objet'"


# ──────────── 5. Non-régression du chemin nominal ────────────────────────────

@refusal_terminal_suite.test()
def test_nom_valide_type_valide_passe() -> None:
    """Nom inconnu, type valide, refused_names vide → (None, False) = chemin nominal."""
    msg, add = check_add_entity_guards(
        "la forteresse des Cendral", "lieu", set(), _PROF
    )
    assert msg is None, "le chemin nominal ne doit pas être bloqué"
    assert add is False


@refusal_terminal_suite.test()
def test_refused_names_vide_ne_bloque_pas_personnage() -> None:
    """refused_names={} = aucun refus mémoire — non-régression base vierge."""
    msg, add = check_add_entity_guards(
        "Tornel le guetteur", "personnage", set(), _PROF
    )
    assert msg is None
    assert add is False


# ──────────── Anti-leakage ──────────────────────────────────────────────────

@refusal_terminal_suite.test()
def test_no_test_names_in_prompts() -> None:
    """Les noms de test n'entrent JAMAIS dans les prompts des agents (src/felix/)."""
    src = pathlib.Path(__file__).parents[3] / "src" / "felix"
    leaked = []
    for py in src.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for name in _TEST_NAMES:
            if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
                leaked.append(f"{name} dans {py.relative_to(src.parent.parent)}")
    assert not leaked, f"noms de test présents dans les sources : {leaked}"
