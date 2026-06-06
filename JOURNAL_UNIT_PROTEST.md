# Journal migration pytest → protest (unit tests)

## 2026-03-28 — Debut de migration

### Baseline
- 145 tests pytest collectes (`uv run python -m pytest --co -q`)
- 8 fichiers test, 1 conftest.py

### Notes pre-migration
- protest installe en editable depuis `../protest`
- Deja utilise pour les evals (evals/session.py), premiere utilisation pour des tests unitaires/integration

---

## Observations en cours de migration

### `from __future__ import annotations` + `TYPE_CHECKING` = DI cassee

**Probleme** : Quand on utilise `from __future__ import annotations` avec `if TYPE_CHECKING: from neo4j import AsyncDriver`, protest ne pouvait pas resoudre les annotations `Annotated[AsyncDriver, Use(seeded_driver)]` au runtime. Le type `AsyncDriver` n'etait pas defini dans le namespace du module → erreur `missing 1 required positional argument`.

**Fix cote protest** : Commit `30aca24` — `get_type_hints_compat` est maintenant utilise dans les 4 sites de resolution DI. Les imports `TYPE_CHECKING` fonctionnent partout. On a pu remettre les imports derriere `TYPE_CHECKING` comme avant.

### `--dry-run` n'existe pas

Le flag `--dry-run` n'existe pas dans `protest run`. Il faut utiliser `--collect-only`. Pas grave mais le plan de migration dans plans/ mentionnait `--dry-run`. Penser a ajouter `--dry-run` comme alias.

### Teardown session-scoped async fixture : event loop mismatch

**Probleme** : A la fin du run, le teardown de `neo4j_driver` (session-scoped, async) crash avec `RuntimeError: Task got Future attached to a different loop`. Le driver Neo4j essaie de fermer ses connexions sur un event loop qui n'est plus le bon.

**Impact** : Aucun — tous les tests passent, c'est juste un warning post-run dans stderr. Mais c'est bruyant.

**Comparaison pytest** : pytest-asyncio gere ca avec son propre event loop policy. protest semble creer un nouveau loop pour le teardown des fixtures session-scoped, ce qui casse les drivers async qui gardent une reference a l'ancien loop.

**Fix cote protest** : Commit `4df0d09` — remplace `run_in_executor` + nouveau loop par `asyncio.create_task` sur le meme loop. Le `await drv.close()` fonctionne maintenant proprement dans le teardown.

### Concurrence -n 4 : ChromaDB + Neo4j

**Probleme** : En `-n 4`, deux types de race conditions :
1. ChromaDB `EphemeralClient()` a un singleton interne pas thread-safe → crash quand plusieurs fixtures creent un client en parallele
2. Plusieurs suites integration tournent en parallele, chacune fait seed/DETACH DELETE sur le meme Neo4j → corruption des donnees

**Mauvais fix** : `max_concurrency=1` sur les suites — serialise TOUT dans la suite, y compris les tests mock-only qui pourraient tourner en parallele.

**Bon fix** : `max_concurrency=1` sur les fixtures (`seeded_driver`, `chroma_collection`). Protest serialise uniquement les tests qui UTILISENT la ressource partagee. Les tests sans DB restent paralleles.

### Ce qui manque vs pytest

- **`pytest.approx`** : Pas d'equivalent dans protest. On remplace par `abs(x - y) <= tol`. Minor mais un `approx()` builtin serait bienvenu.
- **`@patch` comme decorateur de test** : En pytest, `@patch("module.func")` injecte le mock comme parametre supplementaire du test. Pas possible en protest (les params sont reserves au DI). Fix : utiliser `with patch(...):` dans le corps du test. C'est en fait plus explicite, donc pas vraiment un manque.
- **Pas de `conftest.py` automatique** : Tout est explicite (fixtures.py + session.py). C'est voulu et c'est mieux. Le seul inconvenient est le boilerplate `Annotated[T, Use(fixture)]` sur chaque parametre — plus verbeux que le nom-magique de pytest.

---

## Resultat final

- **145/145 tests protest** passent (`uv run protest run tests.session:session`)
- **53 unit** + **92 integration**
- **~9s en -n 20, ~20s en -n 1** (les tests sync tournent en parallele, Neo4j serialise via `max_concurrency=1` sur `seeded_driver`)
- Anciens fichiers pytest supprimes (conftest.py + 8 test_*.py)

### Clean-up post-migration

- Suites intermediaires `unit/suite.py` et `integration/suite.py` — hierarchie `::Unit::Resolver` fonctionne
- Helpers `_insert_character`/`_get_char` extraits dans `integration/helpers.py` — plus de duplication
- Tags `neo4j` et `chromadb` sur les fixtures — `--no-tag neo4j` donne 62 tests (53 unit + 9 mock-only integration)
- Tags `unit`/`integration` herites des suites parentes — retires des suites enfants
