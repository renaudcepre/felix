# Code Review — Felix Screenplay Assistant

**Date** : 2026-03-23
**Scope** : tout le code source (`src/felix/`, `tests/`, `evals/`, `web/`)
**Reviewer** : Claude Opus 4.6

---

## Resume executif

Felix est un projet bien structuré avec un pipeline d'ingest sophistiqué,
une couche graph Neo4j propre, et un frontend Vue/Nuxt fonctionnel.
La qualité globale est bonne — config Ruff stricte, mypy strict, bonne
séparation frontend/backend, usage correct de pydantic-ai.

Les axes d'amélioration les plus impactants :

1. `repository.py` est un God Module (1021 lignes, ~15 domaines mélangés)
2. Usage systématique de `dict[str, Any]` là où des modèles typés élimineraient des bugs
3. Des fonctions privées (`_build_model`, `_emit`, `_normalize`) exportées et utilisées
   partout
4. Des écritures Neo4j séquentielles évitables avec `UNWIND`
5. `run_import_pipeline` a trop de responsabilités (3 noqa: PLR supprimés)

---

## 1. Architecture & Responsabilités

### 1.1 ~~`repository.py` — God Module~~ ✅ FAIT

**Fichier** : ~~`src/felix/graph/repository.py` (1021 lignes)~~ supprimé
**Severite** : ~~Haute~~ Résolu

~~Ce module unique gère les requêtes Cypher pour tous les domaines.~~

Résolu : découpé en 7 modules domaine dans `graph/repositories/` :
`characters.py`, `groups.py`, `locations.py`, `scenes.py`, `timeline.py`,
`issues.py`, `beats.py`. Re-export via `__init__.py`.

### 1.2 ~~`_build_model` — fonction privée exportée partout~~ ✅ FAIT

**Fichier** : ~~`src/felix/agent/chat_agent.py:47`~~ → `src/felix/llm.py`
**Severite** : ~~Moyenne~~ Résolu

Résolu : `_build_model` renommée `build_model` et déplacée dans `src/felix/llm.py`.
5 importeurs mis à jour.

### 1.3 Dépendance circulaire `pipeline.py` ↔ `orchestrator.py`

**Fichiers** : `ingest/pipeline.py`, `ingest/orchestrator.py`
**Severite** : Moyenne

- `pipeline.py` importe `SceneOrchestrator`, `make_scene_id` depuis `orchestrator.py`
- `orchestrator.py` importe `_PipelineContext` depuis `pipeline.py` (via
  `TYPE_CHECKING`)

La guard `TYPE_CHECKING` évite le crash, mais la structure reste fragile.
`_PipelineContext` devrait vivre dans un module tiers (`ingest/context.py`)
ou bien `orchestrator.py` ne devrait pas en dépendre.

### 1.4 ~~`run_import_pipeline` — trop de responsabilités~~ ✅ FAIT

**Fichier** : `ingest/pipeline.py`
**Severite** : ~~Haute~~ Résolu

Résolu : extrait en 4 sous-fonctions (`_segment_scene_files`,
`_create_agents`, `_process_scene_unit`, `_process_all_scenes`,
`_setup_pipeline`). PLR0912 et PLR0915 supprimés de `run_import_pipeline`.

### 1.5 ~~`resolution.py` exporte des fonctions "privées"~~ ✅ FAIT

**Fichier** : `ingest/resolution.py`
**Severite** : ~~Faible~~ Résolu

Résolu : préfixe `_` retiré de `emit`, `handle_ambiguous_character`,
`resolve_characters`, `resolve_location`.

---

## 2. Typage & Sécurité de type

### 2.1 ~~`dict[str, Any]` comme type de retour du repository~~ ✅ FAIT

**Fichier** : `src/felix/graph/repositories/_types.py`
**Severite** : ~~Haute~~ Résolu

~~Toutes les fonctions repository retournent `dict[str, Any]`.~~

Résolu : 20 `TypedDict` dans `_types.py`, 19 fonctions de lecture typées
avec `cast()` string (no-op runtime). Pattern deux classes pour les nodes
avec champs optionnels (`_Required` + `total=False`). Imports sous
`TYPE_CHECKING` — zéro coût runtime.

### 2.2 `Any` pour les agents dans `SceneOrchestrator`

**Fichier** : `ingest/orchestrator.py:74-81`
**Severite** : Moyenne

```python
@dataclass
class SceneOrchestrator:
    analyzer: Any
    timeline_checker: Any
    narrative_checker: Any
    profiler: Any = None
    # ...
```

Ces champs devraient être `AnalyzerAgents`, `Agent[None, ConsistencyReport]`,
`Agent[None, CharacterProfile]`, etc. L'usage de `Any` annule le bénéfice
de `mypy --strict`.

### 2.3 ~~`ConsistencyIssue.type` et `.severity` — `str` au lieu de `Literal`~~ ✅ FAIT

**Fichier** : `ingest/models.py`
**Severite** : ~~Faible~~ Résolu

Résolu : `type` et `severity` typés avec `Literal`.

### 2.4 `ChatAgent` TypeAlias perd l'information de type

**Fichier** : `api/deps.py:49`
**Severite** : Faible

```python
ChatAgent: TypeAlias = Annotated[Agent, Depends(get_agent)]
```

`Agent` est non-paramétré — on perd `Agent[FelixDeps, str]`.
Devrait être `Annotated[Agent[FelixDeps, str], Depends(get_agent)]`.

### 2.5 `list[object]` pour message_history dans le CLI

**Fichier** : `cli.py:52`
**Severite** : Faible

`message_history: list[object] = []` devrait utiliser les types pydantic-ai
(`list[ModelMessage]`) pour bénéficier du typage.

---

## 3. Bugs potentiels & Code risqué

### 3.1 ~~`datetime.now()` sans timezone dans l'export CLI~~ ✅ FAIT

**Fichier** : `cli.py`
**Severite** : ~~Moyenne~~ Résolu

Résolu : `datetime.now(UTC)` dans les deux occurrences.

### 3.2 `entity_checker.py` contourne le repository

**Fichier** : `ingest/entity_checker.py:142-149`
**Severite** : Moyenne

```python
async with driver.session() as session:
    result = await session.run(
        "MATCH (s:Scene) WHERE s.id IN $ids RETURN s.id AS id, s.raw_text AS raw_text",
        ids=scene_ids,
    )
```

Cypher exécuté directement dans une fonction business, byppassant la couche
repository. Si le schéma change, ce query ne sera pas maintenu avec le reste.
Devrait être une fonction dans `repository.py` (ex: `get_scenes_raw_text`).

### 3.3 Suppression temporaire du logger Neo4j

**Fichier** : `repository.py:267-274`
**Severite** : Faible

```python
_notif = logging.getLogger("neo4j.notifications")
_prev = _notif.level
_notif.setLevel(logging.ERROR)
try:
    async with driver.session() as session:
        return await session.execute_read(_read)
finally:
    _notif.setLevel(_prev)
```

Workaround pour masquer des warnings Neo4j. Pas thread-safe, et masque
potentiellement de vrais problèmes. Mieux : filtrer le warning spécifique
avec un `logging.Filter`.

### 3.4 `entity_checker.py` crée un agent à chaque appel

**Fichier** : `ingest/entity_checker.py:194-201`
**Severite** : Faible

```python
model = _build_model(model_name, base_url)
agent: Agent[None, ConsistencyReport] = Agent(
    model, instructions=ENTITY_CHECK_PROMPT, ...
)
result = await agent.run(...)
```

L'agent est recréé à chaque appel de `check_character_consistency`.
Tous les autres agents du pipeline sont créés une fois et réutilisés.
Cet agent devrait suivre le même pattern.

### 3.5 ~~`_normalize` dupliquée~~ ✅ FAIT

**Fichier** : `ingest/utils.py`
**Severite** : ~~Faible~~ Résolu

Résolu : `normalize()` centralisée dans `ingest/utils.py`, supprimée
de `resolver.py` et `entity_checker.py`.

---

## 4. Performance

### 4.1 Ecritures Neo4j séquentielles dans `write_scene` et `load_scene`

**Fichiers** : `writer.py:31-88`, `loader.py:54-72`
**Severite** : Haute

Chaque personnage/groupe est écrit avec un `await tx.run(...)` individuel :

```python
for char in characters:
    await tx.run("MERGE (c:Character {id: $id})...", ...)
    await tx.run("MATCH (c:Character)...", ...)
```

Pour une scène avec 10 personnages, c'est 20 round-trips Cypher dans la
même transaction. `UNWIND` permet de tout faire en 2 requêtes :

```cypher
UNWIND $chars AS char
MERGE (c:Character {id: char.id})
ON CREATE SET c.name = char.name
WITH c, char
MATCH (s:Scene {id: $scene_id})
MERGE (c)-[:PRESENT_IN {role: char.role}]->(s)
```

### 4.2 Export séquentiel dans `export.py`

**Fichier** : `api/routes/export.py:15-27`
**Severite** : Moyenne

9 requêtes Neo4j exécutées séquentiellement :

```python
characters = await repository.list_all_characters_full(driver),
locations = await repository.list_all_locations(driver),
scenes = await repository.list_all_scenes_full(driver),
# ... 6 de plus
```

Toutes sont indépendantes et pourraient être parallélisées avec
`asyncio.gather`.

### 4.3 N+1 query dans `_build_character_detail`

**Fichier** : `api/routes/characters.py:125-153`
**Severite** : Faible

Deux requêtes séparées (`get_character_profile` + `get_character_relations`)
pour construire un `CharacterDetail`. Une seule requête Cypher avec
`OPTIONAL MATCH` suffirait.

### 4.4 `check_scene_consistency` — deux passes LLM séquentielles

**Fichier** : `ingest/checker.py:162-189`
**Severite** : Moyenne

Les deux agents (timeline + narrative) sont appelés séquentiellement.
Ils sont indépendants et pourraient être parallélisés :

```python
timeline_report, narrative_report = await asyncio.gather(
    timeline_agent.run(...), narrative_agent.run(...)
)
```

---

## 5. Sécurité

### 5.1 Pas de validation de taille sur les fichiers uploadés

**Fichier** : `api/routes/ingest.py:56-90`
**Severite** : Moyenne

L'endpoint `/api/import` accepte les fichiers sans limite de taille.
Un fichier de plusieurs GB ferait OOM. Ajouter une vérification :

```python
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
for upload in txt_files:
    content = await upload.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large")
```

### 5.2 Pas de rate limiting sur les endpoints LLM

**Fichiers** : `api/routes/ingest.py`, `api/routes/chat.py`
**Severite** : Faible (local-first)

Pas critique vu le modèle de déploiement local, mais si l'API
est un jour exposée, les endpoints `/api/import` et `/api/chat`
pourraient être abusés (coût LLM, saturation Neo4j).

### 5.3 CORS hardcodé pour le dev

**Fichier** : `api/main.py:50-55`
**Severite** : Faible

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3007"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

L'origin est hardcodée. Devrait être configurable via `settings` pour
faciliter un éventuel déploiement.

---

## 6. DRY & Code dupliqué

### 6.1 Pattern de résolution dupliqué pour characters et locations

**Fichier** : `ingest/resolution.py`
**Severite** : Moyenne

`_resolve_characters` (lines 173-235) et `_resolve_location` (lines 238-333)
partagent ~80% de leur logique :

- Fuzzy match
- Gestion AmbiguousMatch avec clarification
- Création d'issues
- Emission d'événements SSE
- Gestion du timeout

La duplication est massive (~80 lignes). Un refactor avec un
`_resolve_entity_generic()` qui accepte le type d'entité réduirait
le code de moitié.

### 6.2 ~~Modèle d'embedding configuré en deux endroits~~ ✅ FAIT

**Fichier** : `vectorstore/store.py`
**Severite** : ~~Faible~~ Résolu

Résolu : `_EMBEDDING_MODEL = settings.segmenter_embedding_model`.

### 6.3 `_tmp_path` helper inutile

**Fichier** : `ingest.py:214-217`
**Severite** : Faible

```python
def _tmp_path(tmp_dir: str) -> Path:
    from pathlib import Path
    return Path(tmp_dir)
```

Juste `Path(tmp_dir)` inline ferait l'affaire. Le lazy import de `Path`
n'apporte rien.

---

## 7. Bonnes pratiques pydantic-ai

L'usage de pydantic-ai est globalement correct et idiomatique pour la
version 1.68+ :

- `MistralModel` + `MistralProvider` / `OpenAIModel` + `OpenAIProvider`
- `Agent(model, instructions=..., output_type=..., model_settings=...)`
- `agent.run()`, `agent.iter()` avec streaming
- `ModelMessagesTypeAdapter` pour sérialisation/désérialisation
- `Agent.is_model_request_node()` pour le streaming node-by-node
- `@agent.output_validator` avec `ModelRetry`
- `RunContext[FelixDeps]` pour le DI des tools

**Point d'attention** : le `retries=2` est un bon default pour des modèles 7B,
mais considérer `retries=3` pour les agents critiques (analyzer, profiler)
si le budget le permet.

---

## 8. Tests

### 8.1 Tous les tests sont des tests d'intégration

**Fichier** : `tests/`
**Severite** : Moyenne

Chaque test nécessite une instance Neo4j live. Il n'y a aucun test unitaire
pur (mock du driver). Conséquences :

- CI lente (démarrage Neo4j + cleanup)
- Tests impossibles sans Docker/infra
- Pas de tests isolés du resolver, segmenter (sauf `test_segmenter.py`)

Le segmenter, le resolver (fuzzy matching), les formatters sont
des candidats idéaux pour des tests unitaires purs.

### 8.2 Pas de tests pour le pipeline d'import

**Severite** : Moyenne

L'orchestrator et le pipeline n'ont pas de tests directs (hors evals).
Les evals sont des tests aspirationnels, pas des tests de non-régression.
Un test d'intégration avec un fichier fixture minimal et un mock LLM
sécuriserait les refactors.

---

## 9. Frontend (Vue/Nuxt)

### 9.1 Pas de gestion d'erreur sur les mutations

**Fichier** : `web/app/pages/characters/[id].vue`
**Severite** : Faible

`saveProfile()`, `addRelation()`, `removeRelation()` n'ont pas de
`catch` ni de feedback utilisateur en cas d'erreur réseau/API.
Le `finally` reset le `loading` mais l'erreur est silencieusement ignorée.

### 9.2 Types TypeScript dupliqués avec le backend

**Fichier** : `web/app/types/index.ts`
**Severite** : Faible

Les interfaces TypeScript sont maintenues manuellement en miroir des
modèles Pydantic. Risque de dérive. Considérer un outil de génération
automatique (ex: `datamodel-code-generator` ou `openapi-typescript`
depuis le schéma OpenAPI de FastAPI).

### 9.3 `useFelix` hardcode le pattern SSE

**Fichier** : `web/app/composables/useFelix.ts`
**Severite** : Faible

Le composable implémente la lecture SSE à la main. Partagé avec rien
d'autre — le composable `useImport` fait probablement la même chose.
Un utilitaire `useSSEFetch` réutilisable serait plus propre.

---

## 10. Points positifs (a conserver)

1. **Config Ruff exhaustive** avec `S` (bandit), `ASYNC`, `TCH`, `N` — la
   sécurité et les bonnes pratiques async sont monitorées
2. **Lazy loading du modèle d'embedding** dans `TextSegmenter` — bon pattern
   pour éviter le chargement quand non nécessaire
3. **`TYPE_CHECKING` guards** systématiques pour les imports lourds
   (neo4j, chromadb, sentence_transformers)
4. **Clarification flow** avec asyncio.Event + timeout — design élégant
   pour le human-in-the-loop pendant l'import
5. **Seed data** riche et réaliste dans `graph/seed.py` — excellent pour les tests
6. **Evals framework** séparé de pytest avec des evaluators composables
7. **Prompts LLM bien structurés** avec rules, examples, et anti-patterns explicites
8. **`_coverage_score`** dans le resolver — la pénalité sqrt(n_q/n_c) pour
   éviter les faux positifs token_set_ratio est une bonne trouvaille

---

## Resume des actions recommandees (par priorité)

| #  | Action                                                          | Severite | Effort  |
|----|-----------------------------------------------------------------|----------|---------|
| 1  | ~~Découper `repository.py` en modules domaine~~                 | ✅ Fait  | Moyen   |
| 2  | ~~Typer les retours repository (TypedDict)~~                    | ✅ Fait  | Moyen   |
| 3  | ~~Batch les écritures Neo4j avec UNWIND~~                       | N/A      | —       |
| 4  | ~~Refactorer `run_import_pipeline` en sous-fonctions~~          | ✅ Fait  | Faible  |
| 5  | ~~Renommer `_build_model` → `build_model`, déplacer dans `llm.py`~~ | ✅ Fait  | Faible  |
| 6  | Extraire `_PipelineContext` dans `ingest/context.py`            | Moyenne  | Faible  |
| 7  | Paralléliser l'export avec `asyncio.gather`                     | Moyenne  | Faible  |
| 8  | Paralléliser les deux checker agents                            | Moyenne  | Faible  |
| 9  | ~~Centraliser `_normalize` dans `ingest/utils.py`~~             | ✅ Fait  | Faible  |
| 10 | Ajouter validation de taille sur les uploads                    | Moyenne  | Faible  |
| 11 | ~~Unifier le modèle d'embedding en un seul point de config~~    | ✅ Fait  | Faible  |
| 12 | Ajouter des tests unitaires (resolver, segmenter, formatters)   | Moyenne  | Moyen   |
| 13 | ~~`datetime.now(timezone.utc)` dans l'export CLI~~              | ✅ Fait  | Trivial |
| 14 | ~~Typer `ConsistencyIssue.type/severity` avec Literal~~         | ✅ Fait  | Trivial |

---

## Checklist des taches a realiser

### Phase 1 — Quick wins (effort trivial/faible, impact immediat)

- [x] **`cli.py`** — `datetime.now()` → `datetime.now(UTC)` ✅
- [x] **`ingest/models.py`** — `ConsistencyIssue.type` et `.severity` typés `Literal` ✅
- [x] **`vectorstore/store.py`** — `_EMBEDDING_MODEL` unifié via `settings` ✅
- [x] **`ingest/utils.py`** — `normalize()` centralisée ✅
- [x] **`resolver.py`** — `_normalize` supprimée, importe depuis `utils` ✅
- [x] **`entity_checker.py`** — `_normalize` supprimée, importe depuis `utils` ✅
- [ ] **`api/routes/ingest.py:214-217`** — Supprimer la fonction `_tmp_path`, remplacer
  les appels par `Path(tmp_dir)` directement
- [x] **`agent/chat_agent.py`** — `_build_model` déplacée dans `src/felix/llm.py` ✅
- [x] **5 importeurs** — mis à jour vers `felix.llm.build_model` ✅
- [x] **`resolution.py`** — préfixe `_` retiré de `emit`, `handle_ambiguous_character`,
  `resolve_characters`, `resolve_location` ✅

### Phase 2 — Performance (effort faible, gain mesurable)

- [ ] **`api/routes/export.py:15-27`** — Wrapper les 9 appels repository dans un
  `asyncio.gather` :
  ```python
  chars, locs, scenes, events, char_events, rels, frags, beats, issues = await asyncio.gather(
      repository.list_all_characters_full(driver),
      repository.list_all_locations(driver),
      # ...
  )
  ```
- [ ] **`ingest/checker.py:162-189`** — Paralléliser les appels timeline_agent et
  narrative_agent avec `asyncio.gather`
- [ ] **`graph/writer.py:55-69`** — Remplacer la boucle
  `for char in characters: await tx.run(...)` par une requete
  `UNWIND $chars AS char MERGE (c:Character {id: char.id})...`
- [ ] **`graph/writer.py:71-85`** — Idem pour les groups : remplacer la boucle par
  `UNWIND`
- [ ] **`ingest/loader.py:54-62`** — Remplacer la boucle character upsert + fragment par
  deux requetes `UNWIND`
- [ ] **`ingest/loader.py:65-71`** — Idem pour les groups dans loader
- [ ] **`ingest/loader.py:90-93`** — Idem pour les character events

### Phase 3 — Securite (effort faible)

- [ ] **`api/routes/ingest.py`** — Ajouter une constante
  `MAX_UPLOAD_SIZE = 10 * 1024 * 1024` et verifier `len(content) > MAX_UPLOAD_SIZE`
  apres chaque `await upload.read()`, lever `HTTPException(413)`
- [ ] **`config.py`** — Ajouter un champ
  `cors_origins: list[str] = ["http://localhost:3007"]`
- [ ] **`api/main.py:51`** — Remplacer l'origin hardcodee par `settings.cors_origins`

### Phase 4 — Architecture (effort moyen, impact structurel)

- [x] **Creer `src/felix/graph/repositories/`** avec `__init__.py` ✅
- [x] **Extraire `characters.py`** ✅
- [x] **Extraire `scenes.py`** ✅
- [x] **Extraire `locations.py`** ✅
- [x] **Extraire `timeline.py`** ✅
- [x] **Extraire `issues.py`** ✅
- [x] **Extraire `beats.py`** ✅
- [x] **Extraire `groups.py`** ✅
- [x] **Mettre a jour `graph/repositories/__init__.py`** ✅
- [x] **Mettre a jour tous les imports** ✅
- [x] **Supprimer l'ancien `repository.py`** ✅

### Phase 5 — Refactoring pipeline (effort moyen)

- [ ] **Creer `src/felix/ingest/context.py`** — Y deplacer `_PipelineContext`,
  `ImportProgress`, `ImportStatus` (depuis `resolution.py`)
- [ ] **`ingest/pipeline.py`** — Extraire une fonction
  `_setup_agents(model_name, base_url, enrich_profiles) -> tuple[...]` qui cree tous les
  agents
- [ ] **`ingest/pipeline.py`** — Extraire une fonction
  `_segment_files(scene_files, segmenter, queue) -> list[tuple[Path, int, int, str]]`
- [ ] **`ingest/pipeline.py`** — Extraire une fonction
  `_process_scene_unit(orchestrator, scene_file, scene_id, chunk_text, ...) -> ...` pour
  le corps de la boucle
- [ ] **`ingest/resolution.py`** — Factoriser `_resolve_characters` et
  `_resolve_location` dans une fonction generique
  `_resolve_entity(entity_type, name, registry, aliases, ...)` avec le code de
  clarification partage
- [ ] **`entity_checker.py:142-149`** — Extraire le Cypher brut dans une fonction
  repository `get_scenes_raw_text(driver, scene_ids) -> dict[str, str]`
- [ ] **`entity_checker.py:194-201`** — Transformer `check_character_consistency` pour
  accepter un agent en parametre au lieu de le recreer a chaque appel

### Phase 6 — Typage (effort moyen, fiabilite long terme)

- [x] **`graph/repositories/_types.py`** — 20 TypedDict créés, 19 fonctions de lecture typées ✅
- [ ] **`ingest/orchestrator.py:74-81`** — Remplacer `analyzer: Any` par
  `AnalyzerAgents`, `profiler: Any` par `Agent[None, CharacterProfile] | None`, etc.
- [ ] **`api/deps.py:49`** — Changer `ChatAgent: TypeAlias = Annotated[Agent, ...]` en
  `Annotated[Agent[FelixDeps, str], ...]`
- [ ] **`cli.py:52`** — Remplacer `list[object]` par le type pydantic-ai
  `list[ModelMessage]`
- [ ] **`api/models.py`** — Ajouter `Literal` pour `Issue.type`, `Issue.severity` (en
  plus de `ConsistencyIssue`)

### Phase 7 — Tests (effort moyen)

- [ ] **Creer `tests/test_resolver_unit.py`** — Tests unitaires purs pour
  `fuzzy_match_entity`, `slugify`, `_normalize`, `_coverage_score`,
  `_has_different_first_name` sans Neo4j
- [ ] **Creer `tests/test_segmenter_unit.py`** — Tests supplementaires pour
  `_split_into_blocks`, `_group_blocks`, `_merge_small_segments`, `_apply_overlap` (
  logique pure, pas besoin d'embedding)
- [ ] **Creer `tests/test_formatters_unit.py`** — Tests pour `_format_character_profile`
  avec des dicts en entree (pas de Neo4j)
- [ ] **Creer `tests/test_pipeline_integration.py`** — Test d'integration avec un
  fichier fixture minimal, mock des agents LLM, verification que les nodes Neo4j sont
  crees correctement

### Phase 8 — Frontend (effort faible)

- [ ] **`web/app/pages/characters/[id].vue`** — Ajouter un `catch` avec `useToast()` sur
  `saveProfile()`, `addRelation()`, `removeRelation()` pour afficher les erreurs
- [ ] **`web/nuxt.config.ts`** — Ajouter un script `postbuild` ou `generate:types` qui
  genere `types/index.ts` depuis le schema OpenAPI de FastAPI (via `openapi-typescript`)
- [ ] **`web/app/composables/`** — Extraire un utilitaire `useSSEFetch` reutilisable
  depuis `useFelix.ts` et `useImport.ts`
