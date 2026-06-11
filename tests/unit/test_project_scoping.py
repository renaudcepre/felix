"""Scoping projet/histoire (#60) — garanties STRUCTURELLES contre la contamination.

Deux histoires dans la même base ne doivent JAMAIS se voir (session « Ventilateur /
plaines d'Aragorn » jouée après le dogfood pétrolier : bible mélangée, working set
d'une histoire injecté dans l'autre). Le scoping est porté par une prop `project`
posée EN CODE par les writers et filtrée par TOUS les lecteurs.

Le risque n°1 de ce design est l'OUBLI : une requête Cypher sans le filtre
`project` = contamination silencieuse, invisible tant qu'on ne joue qu'une
histoire. D'où le test structurel : on extrait par AST toutes les chaînes Cypher
qui touchent :GenEntity (ou :UserEdit) dans les modules d'accès, et chacune doit
mentionner `project`. Même esprit que le test anti-leakage des prompts : la loi
est vérifiée sur le CODE, pas sur la bonne volonté.
"""
from __future__ import annotations

import ast
from pathlib import Path

from protest import ProTestSuite

from felix.core.deps import GenericDeps
from felix.core.graph import RESERVED_KEYS
from felix.core.projects import DEFAULT_PROJECT

SRC = Path(__file__).resolve().parents[2] / "src" / "felix"

# Tous les modules qui parlent Cypher au graphe des entités. Un nouveau module
# d'accès DOIT s'ajouter ici (le test échoue par construction s'il passe par
# les helpers existants, déjà scopés).
CYPHER_MODULES = [
    SRC / "core" / "graph.py",
    SRC / "core" / "tools.py",
    SRC / "core" / "projects.py",
    SRC / "core" / "user_edits.py",
    SRC / "api" / "routes" / "entities.py",
]

project_scoping_suite = ProTestSuite("ProjectScoping")


def _cypher_strings(path: Path, marker: str) -> list[tuple[str, str]]:
    """Les littéraux chaîne du module qui sont du Cypher touchant `marker`.

    Détection « Cypher » = la chaîne contient un verbe d'accès (MATCH/MERGE/CREATE
    suivi d'une parenthèse) — les docstrings qui CITENT :GenEntity en prose ne
    comptent pas. Python fusionne les littéraux adjacents au parse : une requête
    écrite en morceaux concaténés est UN seul Constant, analysé en entier.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        text = node.value
        if marker not in text:
            continue
        if not any(verb in text for verb in ("MATCH (", "MERGE (", "CREATE (")):
            continue
        found.append((f"{path.name}:{node.lineno}", text))
    return found


@project_scoping_suite.test()
def test_every_genentity_query_is_project_scoped() -> None:
    """Chaque requête Cypher touchant :GenEntity porte le scoping `project`."""
    missing = []
    seen = 0
    for module in CYPHER_MODULES:
        assert module.exists(), f"module d'accès attendu manquant : {module}"
        for where, query in _cypher_strings(module, ":GenEntity"):
            seen += 1
            if "project" not in query:
                missing.append(f"{where} : {query.strip()[:80]}…")
    assert seen > 0, "aucune requête :GenEntity trouvée — le scan est cassé"
    assert not missing, (
        "Requêtes :GenEntity SANS filtre project (contamination inter-histoires "
        "possible) :\n" + "\n".join(missing)
    )


@project_scoping_suite.test()
def test_user_edit_tombstones_are_project_scoped() -> None:
    """Les tombstones :UserEdit sont scopés : une suppression dans l'histoire A
    ne doit pas s'injecter dans les prompts de l'histoire B."""
    path = SRC / "core" / "user_edits.py"
    queries = _cypher_strings(path, ":UserEdit")
    assert queries, "aucune requête :UserEdit trouvée — le scan est cassé"
    missing = [where for where, q in queries if "project" not in q]
    assert not missing, f"requêtes :UserEdit sans scoping project : {missing}"


@project_scoping_suite.test()
def test_project_is_a_reserved_key() -> None:
    """`project` est posé EN CODE, jamais par le LLM : la clé est réservée
    (invisible des fiches via fmt_props, non-écrasable via props libres)."""
    assert "project" in RESERVED_KEYS


@project_scoping_suite.test()
def test_deps_default_to_default_project() -> None:
    """Sans sélection explicite (evals, anciens appels), tout vit dans le projet
    par défaut — comportement identique à l'avant-#60."""
    field = GenericDeps.__dataclass_fields__["project_id"]
    assert field.default == DEFAULT_PROJECT


@project_scoping_suite.test()
def test_no_global_id_uniqueness_constraint() -> None:
    """La contrainte d'unicité GLOBALE sur e.id est incompatible avec la clé
    composite {id, project} (deux histoires ont chacune leur « camille ») :
    setup_constraints doit la DROP, pas la créer."""
    text = (SRC / "graph" / "driver.py").read_text(encoding="utf-8")
    assert "DROP CONSTRAINT genentity_id_unique" in text
    assert "CREATE CONSTRAINT genentity_id_unique" not in text
