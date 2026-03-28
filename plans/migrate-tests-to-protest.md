# Migration tests pytest → protest

## Context

145 tests pytest dans `tests/`. On veut migrer vers protest pour unifier tests + evals dans le même framework, profiter du `-n` natif, de l'historique, et du DI explicite.

## État actuel

```
tests/
├── conftest.py                    # 2 fixtures : driver, seeded_driver
├── test_character_crud.py         # 15 tests — API FastAPI + httpx (async)
├── test_formatters.py             # 8 tests — agent formatters (async)
├── test_ingest_queries.py         # 20 tests — repository CRUD (async)
├── test_pipeline.py               # 25 tests — pipeline orchestration (async, mocks)
├── test_profiler_and_repository.py # 12 tests — profiler + repository (async)
├── test_resolver.py               # 19 tests — entity resolution (sync)
├── test_segmenter.py              # 29 tests — text segmenter (sync)
├── test_vectorstore.py            # 4 tests — ChromaDB (sync)
├── test_groups.py                 # 8 tests — group CRUD (async)
└── test_consistency.py            # 5 tests — graph checks (async)
```

### Fixtures actuelles (conftest.py)

```python
@pytest.fixture(scope="session")
async def driver() -> AsyncGenerator[AsyncDriver]:
    drv = get_driver()
    await setup_constraints(drv)
    yield drv
    await drv.close()

@pytest.fixture
async def seeded_driver(driver: AsyncDriver) -> AsyncGenerator[AsyncDriver]:
    await seed_graph(driver)
    yield driver
    # teardown: DETACH DELETE all
```

- `driver` = session-scoped, connecte Neo4j
- `seeded_driver` = function-scoped, seed + cleanup entre chaque test

### Dépendances

- Neo4j (docker-compose) — requis pour tous les tests async sauf pipeline (mocké)
- ChromaDB — requis pour vectorstore tests
- Pas de LLM — tout est mocké dans les tests

## Plan de migration

### Phase 1 : Structure + fixtures

Créer `tests/session.py` et `tests/fixtures.py`.

```python
# tests/fixtures.py
from protest import fixture

@fixture()
async def neo4j_driver() -> AsyncIterator[AsyncDriver]:
    drv = get_driver()
    await setup_constraints(drv)
    yield drv
    await drv.close()

@fixture()
async def seeded_driver(
    driver: Annotated[AsyncDriver, Use(neo4j_driver)]
) -> AsyncIterator[AsyncDriver]:
    await seed_graph(driver)
    yield driver
    async with driver.session() as s:
        await s.execute_write(lambda tx: tx.run("MATCH (n) DETACH DELETE n"))
```

```python
# tests/session.py
from protest import ProTestSession
from tests.fixtures import neo4j_driver, seeded_driver
from tests.unit.resolver import resolver_suite
from tests.unit.segmenter import segmenter_suite
from tests.integration.repository import repository_suite
# ...

session = ProTestSession(concurrency=4)
session.bind(neo4j_driver)   # SESSION scope — 1 connexion
# seeded_driver reste non-bind → TEST scope (fresh seed par test)

session.add_suite(resolver_suite)
session.add_suite(segmenter_suite)
session.add_suite(repository_suite)
# ...
```

### Phase 2 : Suites par domaine

Organisation en suites logiques :

```
tests/
├── session.py          # entry point
├── fixtures.py         # shared fixtures
├── unit/
│   ├── resolver.py     # sync, pas de DB
│   ├── segmenter.py    # sync, pas de DB
│   └── vectorstore.py  # sync, ChromaDB only
├── integration/
│   ├── repository.py   # Neo4j CRUD
│   ├── formatters.py   # Neo4j + formatters
│   ├── groups.py       # Neo4j groups
│   ├── consistency.py  # Neo4j graph checks
│   └── api.py          # FastAPI + httpx
└── pipeline/
    └── orchestration.py # mocks, pas de DB
```

### Phase 3 : Conversion test par test

Pattern de conversion :

```python
# AVANT (pytest)
async def test_list_characters(seeded_driver: AsyncDriver) -> None:
    chars = await list_all_characters(seeded_driver)
    assert len(chars) == 5

# APRÈS (protest)
@repository_suite.test()
async def test_list_characters(
    driver: Annotated[AsyncDriver, Use(seeded_driver)]
) -> None:
    chars = await list_all_characters(driver)
    assert len(chars) == 5
```

Pour les tests sync (resolver, segmenter) — pas de fixtures :

```python
# AVANT
def test_slugify_basic() -> None:
    assert slugify("Marie Dupont") == "marie-dupont"

# APRÈS
@resolver_suite.test()
def test_slugify_basic() -> None:
    assert slugify("Marie Dupont") == "marie-dupont"
```

Pour les tests API (FastAPI + httpx) :

```python
# Fixture
@fixture()
async def api_client(
    driver: Annotated[AsyncDriver, Use(seeded_driver)]
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_driver] = lambda: driver
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

# Test
@api_suite.test()
async def test_post_character(
    client: Annotated[AsyncClient, Use(api_client)]
) -> None:
    resp = await client.post("/api/characters", json={"name": "Clara", "era": "2030s"})
    assert resp.status_code == 201
```

### Phase 4 : seeded_driver scope

Le `seeded_driver` est function-scoped en pytest (fresh seed par test). En protest, il ne faut PAS le bind → scope TEST par défaut. Mais le seed + teardown à chaque test est lent.

Alternative : un seul seed pour toute la suite, tests read-only. Les tests qui écrivent utilisent un factory :

```python
@fixture()
async def seeded_driver(
    driver: Annotated[AsyncDriver, Use(neo4j_driver)]
) -> AsyncIterator[AsyncDriver]:
    await seed_graph(driver)
    yield driver
    async with driver.session() as s:
        await s.execute_write(lambda tx: tx.run("MATCH (n) DETACH DELETE n"))

# Bind au niveau suite pour les tests read-only
repository_suite.bind(seeded_driver)  # SUITE scope — seed une fois

# Les tests qui écrivent ont leur propre cleanup
@repository_suite.test()
async def test_upsert_character(
    driver: Annotated[AsyncDriver, Use(seeded_driver)]
) -> None:
    await upsert_character_minimal(driver, {"id": "test-1", "name": "Test", "era": "2020s"})
    # ... assertions
    # cleanup si nécessaire
```

### Phase 5 : CLI

```bash
# Tout
protest run tests.session:session

# Parallèle
protest run tests.session:session -n 8

# Par tag
protest run tests.session:session -t unit
protest run tests.session:session -t integration

# Par keyword
protest run tests.session:session -k "resolver"

# Last failed
protest run tests.session:session --lf
```

## Ordre d'exécution recommandé

1. `tests/unit/resolver.py` — le plus simple, sync, pas de fixtures DB
2. `tests/unit/segmenter.py` — pareil, sync
3. `tests/unit/vectorstore.py` — sync, ChromaDB local
4. `tests/integration/repository.py` — premier avec Neo4j
5. `tests/integration/formatters.py`
6. `tests/integration/groups.py`
7. `tests/integration/consistency.py`
8. `tests/pipeline/orchestration.py` — mocks complexes
9. `tests/integration/api.py` — FastAPI + httpx

## Ce qu'on garde

- Les tests eux-mêmes (assertions, logique) ne changent pas
- Les mocks (unittest.mock.patch) fonctionnent pareil
- Les données de test (fixtures de scènes, etc.) ne bougent pas

## Ce qui change

- Plus de `conftest.py` — fixtures explicites dans `fixtures.py`
- Plus de `pytest.mark.asyncio` — protest gère l'async nativement
- Plus de `AsyncGenerator` en return type — `AsyncIterator` suffit
- `assert` reste `assert` — pas de changement
- `@pytest.fixture(params=...)` → `From(ForEach(...))`
