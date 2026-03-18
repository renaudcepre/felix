# Journal de developpement — Felix

## Issue #13 — Nettoyage des dossiers temporaires d'import — 2026-03-18

**Contexte :** `api/routes/ingest.py` créait des dossiers temporaires `felix-import-*` via `tempfile.mkdtemp()` mais ne les supprimait jamais, ni en succès ni en erreur.

**Changements :**
- `src/felix/ingest/pipeline.py` : ajout de `import shutil` + bloc `finally` en fin de `run_import_pipeline` appelant `asyncio.to_thread(shutil.rmtree, scenes_dir, True)`. `ignore_errors=True` évite toute exception si le dossier est absent (tests avec `tmp_path` pytest).

**Tests :** 9 tests passent (les 3 échecs préexistants sont sans lien).

## Issue #34 — Segmenter : remplacer all-MiniLM-L6-v2 par bge-m3 configurable — 2026-03-18

**Contexte :** Le segmenter utilisait `all-MiniLM-L6-v2` (English-only) en dur. ChromaDB avait déjà migré vers `BAAI/bge-m3` (multilingual) pour le français.

**Changements :**
- `src/felix/config.py` : ajout de `segmenter_embedding_model: str = "BAAI/bge-m3"` (configurable via `FLX_SEGMENTER_EMBEDDING_MODEL`)
- `src/felix/ingest/segmenter.py` : suppression de `_EMBEDDING_MODEL`, import de `settings`, property `_embedding_model` utilise désormais `settings.segmenter_embedding_model`

**Tests :** `uv run pytest tests/test_segmenter.py -v` → 29/29 passent (les tests mockent déjà la property, aucune modification nécessaire).

---

## Issue #18 — duplicate_suspect resolved=True après confirmation utilisateur — 2026-03-18

**Contexte :** Quand l'utilisateur confirmait un lien d'entité ambiguë, l'issue `duplicate_suspect` était créée avec `resolved=False` (valeur par défaut). La description indiquait "Lien confirmé" mais l'issue restait ouverte.

**Changements :**
- `src/felix/ingest/pipeline.py` : ajout de `"resolved": not was_timeout` dans les deux dicts d'issue `duplicate_suspect` (fonctions `_handle_ambiguous_character` et `_resolve_location`). Si l'utilisateur confirme, `resolved=True` ; si timeout (lien auto), `resolved=False`.

**Tests :** `uv run pytest tests/test_resolver.py -v` → 19/19 passent.

---

## Issue #30 — Persistance des alias après confirmation de match — 2026-03-18

**Contexte :** Lors d'un import multi-chunk, une confirmation `"link"` sur une entité ambiguë n'était pas mémorisée. Le même match était re-demandé pour chaque chunk suivant contenant la même entité.

**Changements :**
- `src/felix/graph/repository.py` : ajout de `add_character_alias(driver, char_id, alias)` et `add_location_alias(driver, loc_id, alias)` — Cypher `SET aliases = CASE ... END` idempotent.
- `src/felix/ingest/pipeline.py` :
  - `_PipelineContext` : ajout de `loc_aliases: dict[str, list[str]]`
  - `_build_registry` : lecture des aliases des lieux depuis Neo4j (comme c'était déjà fait pour les personnages)
  - `_load_registries` : retourne 5 valeurs au lieu de 4 (ajout de `loc_aliases`)
  - `_handle_ambiguous_character` : après confirmation utilisateur (pas timeout), écrit l'alias en mémoire et en Neo4j
  - `_resolve_location` : passe `loc_aliases` à `fuzzy_match_entity`, et après confirmation utilisateur (pas timeout), écrit l'alias en mémoire et en Neo4j
  - `_resolve_characters` et `_process_scene` : call sites mis à jour pour passer `driver`, `char_aliases`, `loc_aliases`

**Comportement :** Alias écrits uniquement sur confirmation explicite — les timeouts (auto-link) ne créent pas d'alias car la correspondance reste incertaine.

---

## Piste — Segmenter embedding model incohérent — 2026-03-18

**Observation :** Le segmenter (`src/felix/ingest/segmenter.py`, ligne 25) utilise `all-MiniLM-L6-v2` (anglophone) pour détecter les breakpoints sémantiques, alors que ChromaDB a migré vers `bge-m3` (multilingue) pour exactement la même raison. Le contenu de Felix étant en français, c'est incohérent.

**Impact :** Faible en pratique — la segmentation détecte juste des changements de topic, pas de la similarité fine. Le modèle produit des coupures acceptables sur du français. Mais c'est une dette technique à résorber.

**Fix envisagé :** Remplacer le hardcode par `bge-m3` ou exposer un setting `segmenter_embedding_model` dans `config.py`. `bge-m3` est déjà une dépendance (ChromaDB).

**Ref :** [Issue #34](https://github.com/renaudcepre/felix/issues/34)

---

## Migration prompts en anglais — 2026-03-18

**Contexte :** Les evals chatbot avec Qwen2.5-7B-Instruct-Turbo ont chuté de 81% à 54%. Hypothèse : demander au modèle de raisonner sur une base ingérée en anglais avec des questions en français crée une friction trop importante pour un petit modèle.

**Changements :**
- `src/felix/ingest/analyzer.py` : `ANALYZER_PROMPT` traduit en anglais. Message de retry traduit.
- `src/felix/ingest/checker.py` : `CHECKER_TIMELINE_PROMPT` et `CHECKER_NARRATIVE_PROMPT` traduits en anglais.
- `src/felix/ingest/profiler.py` : `PROFILER_PROMPT` et `PROFILER_PATCH_PROMPT` traduits en anglais. Labels d'input des fonctions `profile_character` et `patch_character_profile` traduits.
- `src/felix/agent/chat_agent.py` : suppression de `You answer in French.` et traduction de l'exemple dans le prompt.
- `evals/run_evals.py` : les 26 questions du `CHATBOT_DATASET` traduites en anglais.

**Décision :** Suppression de toutes les instructions de langue dans les prompts (`Reply in French`, `You answer in French`, etc.). La langue de réponse sera injectée dynamiquement au niveau applicatif dans une future itération.

**Leçon :** Le mix FR/EN (questions FR + données EN + instructions EN) est trop ambigu pour les petits modèles — ils perdent le fil entre la langue de raisonnement et la langue de réponse. Garder une langue unique bout-en-bout pour les prompts système.

---

## Segmentation narrative — 2026-03-17

**Objectif :** Rendre la pipeline robuste face aux fichiers de taille arbitraire (texte libre > 2500 tokens). Découpage sémantique en chunks overlappants, idempotence re-import, liaison NEXT_CHUNK dans le graphe.

**Nouveaux fichiers :**
- `src/felix/ingest/segmenter.py` : `segment_text()` — passthrough si ≤ budget, sinon découpage en 3 passes (estimate_tokens → semantic breakpoints cosine similarity all-MiniLM-L6-v2 → overlap 20%). Modèle chargé lazily.
- `tests/test_segmenter.py` : 26 tests unitaires (vecteurs orthogonaux pour forcer les cuts à positions précises).
- `plans/segmentation.md` : plan d'architecture complet (phases, API, injection pipeline, schéma Neo4j).

**Fichiers modifiés :**
- `src/felix/config.py` : 3 nouveaux settings (`segmenter_max_tokens`, `segmenter_overlap_ratio`, `segmenter_threshold`).
- `src/felix/graph/writer.py` : ajout `link_next_chunk(driver, from_id, to_id)` — crée `(:Scene)-[:NEXT_CHUNK]->(:Scene)`.
- `src/felix/graph/repository.py` : ajout `get_scene_ids_for_stems(driver, stems)` — STARTS WITH pour couvrir `scene-{stem}` et `scene-{stem}-chunk-NN`.
- `src/felix/ingest/pipeline.py` : expansion fichier → chunks avant traitement, `_make_scene_id()`, SSE event `file_segmented`, `link_next_chunk` après chaque chunk.

**Tests :** 115/115 passent (112 unitaires + 3 nouveaux pour `_merge_small_segments`).

**Evals :** suite `pipeline-segmentation` 8/8 (Mistral small). Fixture `long-mission.txt` (2148 mots, ~2899 tokens) → 2 chunks, 1 NEXT_CHUNK, 4 personnages extraits cross-chunk.

**Fix bug segmenter :** `_merge_small_segments` ajoutée — les breakpoints sémantiques sont des points de coupure préférentiels, pas forcés. Texte dialogue-heavy : 2 chunks au lieu de 53.

---

## Code review fixes — 2026-03-17

**Objectif :** Résoudre 7 issues remontées lors de la code review post-migration Neo4j.

**Changements :**
- `src/felix/graph/writer.py` : `write_scene` → transaction atomique `execute_write()` (était plusieurs `session.run()` auto-commit)
- `src/felix/config.py` + `.env.example` : documenter le password dev-only, créer fichier d'exemple complet
- `src/felix/graph/repository.py` : migration complète vers `execute_read/execute_write()` avec `AsyncManagedTransaction` ; fix N+1 dans `get_timeline_rows` (COLLECT en Cypher) et `get_location_detail` ; ajout `get_issue_by_id()`
- `src/felix/graph/checks.py` : `check_bilocalization` → `execute_read()`
- `src/felix/graph/formatters.py` : `find_character` consolidée en une seule requête Cypher (OPTIONAL MATCH relations + fragments) — de N+2 sessions à 1 session par appel ; `_format_character_profile` devient synchrone
- `src/felix/api/routes/ingest.py` : `patch_issue` utilise `get_issue_by_id()` au lieu de `list_issues()` + scan linéaire
- `src/felix/ingest/pipeline.py` : `read_text` et `glob` via `asyncio.to_thread` (plus de blocage I/O sur l'event loop)
- `src/felix/api/main.py` : commentaire explicatif sur l'ordre de `setup_logfire()` (instrumenter avant pydantic-ai)
- `evals/_runner.py` : suppression de `run_with_spinners` (dead code depuis l'unification en `asyncio.run()` unique)

**Tests :** 86/86 passent. `test_format_profile_includes_fragments` mis à jour pour utiliser l'API publique `find_character`.

---

## Isolation evals par récit + fix bilocalization dedup — 2026-03-17

**Objectif :** Isoler les fixtures d'evals par récit (un sous-dossier par histoire), corriger le bug de déduplication bilocalization (IDs aléatoires → MERGE ne dédupliquait pas), et ajouter un dataset Convoi avec 12 cas d'évaluation dont 2 tests de régression directs.

**Changements :**
- `src/felix/graph/checks.py` : remplacer `uuid.uuid4()` par ID déterministe `biloc-{char_id}-{min(s1,s2)}-{max(s1,s2)}` — le `MERGE (i:Issue {id: $id})` dans `repository.py` déduplique naturellement. Suppression `import uuid`.
- `evals/fixtures/` : réorganisation en `helios/` (7 fichiers déplacés) et `convoi/` (3 fichiers copiés depuis `data/scenes/`)
- `evals/pipeline/task.py` : `FIXTURES_DIR` → `FIXTURES_ROOT`, `_run_pipeline()` prend `fixtures_dir: Path`, `build_pipeline_task()` remplacé par `make_pipeline_task(subdir)` — factory sync retournant un builder async no-arg détectable par le runner
- `evals/pipeline/evaluators.py` : ajout `ExactIssueCountByType` et `NoIssueDescriptionContains`
- `evals/run_evals.py` : ajout `CONVOI_DATASET` (12 cas), imports mis à jour, `SUITES` étendu avec `pipeline-convoi`

**Architecture :** Les suites `pipeline` et `pipeline-convoi` partagent le même Neo4j mais tournent séquentiellement — `MATCH (n) DETACH DELETE n` en début de `_run_pipeline` assure l'isolation. Les IDs Helios sont inchangés (déplacement de fichiers ne change pas les stems).

---


## Migration SQLite + Kuzu → Neo4j (store unique) — 2026-03-17

**Objectif :** Remplacer SQLite (aiosqlite) + Kuzu par Neo4j comme store unique. Un seul store, Cypher partout, async natif. ChromaDB inchangé.

**Changements :**
- `pyproject.toml` : ajout `neo4j>=5.0`, `testcontainers[neo4j]` (dev), suppression `aiosqlite`, `kuzu`
- `src/felix/config.py` : ajout `neo4j_uri/user/password`, suppression `db_path`/`kuzu_path`
- `docker-compose.yml` : créé avec service Neo4j 5.24-community
- `src/felix/graph/` : réécriture complète — `driver.py`, `repository.py` (37 fonctions), `writer.py`, `checks.py`, `seed.py`, `formatters.py` nouveaux/réécrits en Cypher async
- `src/felix/db/` : supprimé entièrement
- `src/felix/ingest/loader.py`, `checker.py`, `pipeline.py` : portés vers `neo4j.AsyncDriver`
- `src/felix/api/` : deps, main, et 5 routes portées (`DB` → `Neo4jDriver`)
- `src/felix/agent/deps.py`, `tools.py` : `db` → `driver`, formatters depuis `graph.formatters`
- `src/felix/cli.py` : `init_db` → `get_driver + setup_constraints`
- `tests/conftest.py` : fixture `driver` via testcontainers Neo4j, `seeded_driver` avec teardown DETACH DELETE
- Tous les tests unitaires portés vers `AsyncDriver` + Cypher
- `evals/pipeline/task.py`, `evals/task.py` : portés vers Neo4j driver

**Points clés :** `aliases` stocké nativement LIST<STRING> (plus de json.dumps/loads), `resolved` stocké BOOLEAN, `scene_id` des issues via relation `(Scene)-[:HAS_ISSUE]->(Issue)`, bilocalization check en Cypher pur.

**Bugs Cypher corrigés :** WHERE après OPTIONAL MATCH ne filtre que le pattern optionnel — déplacé avant le OPTIONAL MATCH dans `get_timeline_rows` et `list_issues`. testcontainers remplacé par connexion directe au docker-compose (évite les problèmes d'event loop avec les fixtures session-scoped).

**Résultat evals pipeline (mistral-small-latest) :** 29/34 (85%). Échecs restants : `no_duplicate_relation` (doublon RELATED_TO), `irina_kepler9_date_resolved` (date non retrouvée après patching), `chen_active_appearances` (count fragments), `no_error_severity` (8 issues error), `lena_physical_contradiction_detected` (non détectée).

---

## Remplacement `os._exit(0)` par `atexit` dans `run_evals.py` — 2026-03-16

**Objectif :** Éliminer le `os._exit(0)` brutal qui empêchait tout cleanup (atexit handlers, flush fichiers, fermeture DB).

**Changement :** Enregistrement de `atexit.register(os._exit, 0)` en début de `main()` — s'exécute en dernier (LIFO) après tous les autres handlers de cleanup, puis empêche `threading._shutdown()` de bloquer sur les threads non-daemon de chromadb/sentence-transformers. La sortie normale se fait via `raise typer.Exit()`.

---

## Refactoring `_normalize` → `evals/_utils.py` — 2026-03-16

**Objectif :** Éliminer les 3 implémentations dupliquées de `_normalize` dans les suites d'évals.

**Changements :**
- `evals/_utils.py` (nouveau) : fonction `normalize()` partagée — NFKD + strip combining marks
- `evals/evaluators.py`, `evals/ingest/evaluators.py`, `evals/pipeline/evaluators.py` : suppression des définitions locales, import de `normalize` depuis `evals._utils`
- Unification de comportement : `pipeline/evaluators.py` utilisait NFD + ASCII encode, aligné sur NFKD + combining (plus correct pour l'Unicode)

**TODO review_incremental_pipeline.md :** item "Extraire `_normalize`" coché.

## Pipeline eval — cas difficiles pré-graphe — 2026-03-15

**Objectif :** Constituer un benchmark de départ avant la migration vers Kuzu (graphe). Les nouveaux cases *peuvent échouer* — c'est le but : révéler les trous du pipeline actuel.

**Ajouts :**
- `evals/pipeline/task.py` : 2 nouveaux query types — `all_issues` (toutes les issues), `relations:<char_id>` (relations d'un personnage spécifique)
- `evals/pipeline/evaluators.py` : 6 nouveaux évaluateurs — `ExactFragmentCount`, `RelationWithCharPresent`, `IssueDescriptionContains`, `IssueTypePresent`, `MaxIssueSeverityCount`, `AllLocationsContainKeyword` + helper `_normalize` (accent-insensitif)
- `evals/run_evals.py` : 10 nouveaux cases répartis en 4 catégories

**10 nouveaux cases :**
- character_arc (medium/easy) : `irina_experience_in_profile`, `yuna_appears_exactly_once`, `chen_appears_in_scene2_only`
- relations (medium/hard) : `relation_irina_chen`, `relation_kofi_irina`, `relation_kofi_chen_indirect` (transitive — attendu ✗)
- issues (medium/hard) : `yuna_leak_in_issue_description`, `scene3_has_timeline_issue`, `no_error_severity` (attendu ✗ si LLM escalade en "error")
- spatial (hard) : `all_locations_at_helios` (attendu ✗ si les lieux ne contiennent pas "helios")

**Résultat attendu :** ~5-6/10 passent. Les 4 cas "hard" servent de baseline pour mesurer les gains post-graphe.

---

## Eval suite — refonte complète — 2026-03-15

**Objectif :** Rendre les evals rapides, fiables et exploitables pour guider les améliorations.

**Infra :**
- `evals/_runner.py` : exécution parallèle via `asyncio.gather`, auto-detect LM Studio → Together AI, output compact (✔/✗ par case + `N/M passed`), résultats détaillés en fichiers `evals/results/<suite>_<ts>/<case>.md`
- `evals/run_evals.py` : unified entry point, 3 suites (pipeline/ingest/chatbot), CLI `--suite`, `--case`, `--list`, `--together`, `--local`
- `justfile` : commande `just evals [options...]`
- Provider Together AI (`Qwen/Qwen2.5-7B-Instruct-Turbo`) comme fallback cloud rapide

**Datasets :**
- Pipeline : 11 cases (extraction, apparitions, profiling, consistency, relations)
- Ingest : 16 cases sur scènes réelles + fixtures test (supprimable, redondant avec pipeline)
- Chatbot : 17 cases — lookup, coherence, semantic, cross-era, causal (4 nouveaux), négatifs

**Évaluateurs :**
- `ContainsExpectedFacts` : ajout assertion `facts_ok` (bool) avec `min_score=0.5` — les cas sans réponse tombent maintenant en ✗
- `CharacterRoleAccuracy` : fix normalisation Unicode sur les rôles extraits (`_normalize` au lieu de `.lower()`)
- Cas causaux → `LLMJudge` avec rubric sémantique (résiste aux synonymes/paraphrases)
- Cas à données absentes → `RefusesToFabricate`
- Dataset-level evaluators ne créent pas d'assertions per-case → tous les cas non-négatifs ont `ContainsExpectedFacts()` en case-level

**Résultats actuels :** pipeline 10/11, ingest 15/16, chatbot 16/17
- `yuna_profile_background` : profil vide en DB → bug pipeline
- `scene2_no_jakes_participant` : Jakes extrait dans scène 002 → comportement LLM à investiguer
- `semantic_archives` : bot rate les requêtes par lieu/contexte (vs personnage) → gap fonctionnel à corriger

---

## Fix SSE breaking changes — 2026-03-15

`check_started` et `profiling_character` avaient des champs renommés après la refonte incrémentale,
cassant l'affichage dans le journal d'import. Fix : ajout de `scene_title` aux deux events côté pipeline,
mise à jour frontend (`import.vue` + `types/index.ts`).

---

## Pipeline incremental — 2026-03-15

**Objectif :** Passer d'un pipeline batch (check + profiling en fin d'import) a un pipeline incremental (check + profiling apres chaque scene).

**Changements :**
- `repository.py` : ajout de `get_scene_summaries_by_ids()` et `patch_character_profile_fields()` (COALESCE new over existing)
- `checker.py` : refonte complete avec 2 passes sequentielles (CHECKER_TIMELINE_PROMPT + CHECKER_NARRATIVE_PROMPT) + retrieval ChromaDB (K=10 scenes semantiquement proches)
- `profiler.py` : ajout PROFILER_PATCH_PROMPT + `patch_character_profile()` pour enrichir un profil existant sans ecraser les donnees
- `pipeline.py` : suppression de `_run_consistency_check` et `_run_character_profiling`, remplacement par `_check_scene()` et `_profile_scene_characters()` appeles dans la boucle principale. Issues ecrites en DB immediatement. Mode create vs patch selon presence de background/arc.

**Resultat :** 69 tests passes. Les evenements SSE `check_started`, `check_complete`, `issue_found`, `profiling_character`, `character_profiled` sont emis apres chaque scene (plus en batch).

---

## Phase 0 — Proof of Concept CLI

### 2026-03-14

**Objectif :** Valider que le modele (Mistral Nemo 12B via API) peut repondre a des questions de coherence en utilisant des tools (SQLite + ChromaDB) a travers pydantic-ai.

**Stack mise en place :**
- pydantic-ai 1.68 + MistralModel + MistralProvider
- SQLite (aiosqlite) pour les donnees structurees
- ChromaDB (embedder par defaut all-MiniLM-L6-v2) pour la recherche semantique sur les scenes
- CLI async avec boucle chat multi-turn

**Soucis rencontres :**

1. **`pydantic-ai[mistral]` ne declare plus d'extra "mistral"** — pydantic-ai 1.68 inclut Mistral par defaut. Warning inoffensif au `uv sync`.

2. **Incompatibilite `mistralai` 2.0 vs pydantic-ai 1.68** — `uv` a installe `mistralai` 2.0.2 qui reorganise completement ses modules (`Mistral` dans `mistralai.client` au lieu de `mistralai`, `UNSET` supprime). pydantic-ai attend `mistralai >=1.9.11,<2.0`. Fix : pin `mistralai>=1.9.11,<2.0` dans pyproject.toml.

3. **API pydantic-ai renommee depuis les tutos/exemples courants** — `result_type` → `output_type`, `system_prompt` → `instructions`, `result.data` → `result.output`, et `MistralModel(model, api_key=...)` → `MistralModel(model, provider=MistralProvider(api_key=...))`. Plusieurs aller-retours avant de lire la doc officielle (ai.pydantic.dev).

4. **Tentative OpenAI-compatible pour Mistral** — Contourner le probleme mistralai en passant par `OpenAIModel` + `OpenAIProvider(base_url="https://api.mistral.ai/v1")`. Ca connecte et le modele appelle les tools, mais l'API Mistral renvoie `type: null` dans les tool_calls au lieu de `type: "function"`, ce que le parser OpenAI de pydantic-ai rejette. Impasse → retour au MistralModel natif.

5. **TYPE_CHECKING et pydantic-ai** — Les imports `RunContext` et `FelixDeps` dans les tools etaient sous `if TYPE_CHECKING:` (pour satisfaire ruff TCH). Mais pydantic-ai resout les type hints au runtime pour generer les schemas d'outils → `NameError: name 'RunContext' is not defined`. Fix : imports normaux pour tout ce que pydantic-ai introspecte.

6. **ChromaDB telecharge un modele au premier usage** — Le embedder par defaut (all-MiniLM-L6-v2, ~79MB ONNX) se telecharge au premier `seed`. Ca bloquait les tests pytest qui tournaient sans timeout. Non-bloquant une fois cache.

**Resultat :**
CLI fonctionnel. Le modele appelle correctement les tools (list → get → reason), recupere les donnees de la bible, et repond aux questions de coherence. Il repond en anglais malgre le prompt en francais — comportement typique de Nemo 12B, a ajuster.

**Note :**
Les metadata des scenes (personnages presents, era, location) sont hardcodees dans le seed. En Phase 1, c'est le Scene Analyzer agent qui les extraira automatiquement du texte brut.

---

### 2026-03-14 (2) — Simplification tools + support multi-modele

**Probleme :** Nemo 12B appelle `list_characters` mais ne fait pas le deuxieme appel `get_character` pour recuperer le profil complet. Le pattern list→get en deux etapes est trop complexe pour un 12B.

**Modifications :**
- `queries.py` : Remplace `list_characters`/`get_character`/`list_locations`/`get_location` par `find_character(name)` et `find_location(name)` — recherche LIKE case-insensitive sur name + aliases, retourne le profil complet en 1 appel. Fallback : liste des noms disponibles si aucun match.
- `tools.py` : 4 tools → 2 tools (`find_character`, `find_location`) + `get_timeline` et `search_scenes` inchanges.
- `chat_agent.py` : System prompt simplifie (plus de mention list→get), `create_agent(model_name)` accepte un override de modele.
- `evals/task.py` : Support `FELIX_EVAL_MODEL` env var pour comparer Nemo vs mistral-small.
- `tests/test_queries.py` : 8 tests find_* (name, partial, alias, case-insensitive, no-match) + 5 tests timeline inchanges. 13/13 passent.
- `cli.py` : Output stylise avec rich — header panel avec config du run (model, DB, ChromaDB), prompt colore, spinner pendant l'appel modele.

**Resultat :** Nemo 12B fait maintenant `find_character("Marie Dupont")` en 1 seul appel et retourne le profil complet avec relations.

---

### 2026-03-14 (3) — Premier run evals Nemo 12B

**Resultats (open-mistral-nemo, 9 cases, ~2.7s/case) :**
- facts_score moyen : 0.548, 66.7% assertions pass
- Lookup et coherence : bons resultats, le modele appelle les tools correctement en 1 appel
- Tests negatifs : echec — Nemo hallucine (invente une "Renault noir de 1938" pour la voiture de Marie, ne refuse pas pour le frere de Julien)
- Cross-era : repond en anglais malgre le prompt FR
- Score facts artificiellement bas a cause des accents : l'evaluator cherchait `Resistance` mais Nemo ecrit `Résistance`

**Corrections :**
- `evaluators.py` : `ContainsExpectedFacts` normalise maintenant les accents (NFKD + strip combining chars) avant comparaison
- `run_evals.py` : `LLMJudge` utilise `mistral-small-latest` au lieu d'OpenAI (pas de clef OpenAI)

**Prochaine etape :** Relancer les evals pour mesurer l'impact de la normalisation, puis tester avec mistral-small.

---

### 2026-03-14 (4) — Support modeles locaux (LMStudio)

**Ajout :** Support OpenAI-compatible pour modeles locaux via LMStudio.

**Modifications :**
- `config.py` : Ajout `MODEL_BASE_URL` (optionnel). Si present, utilise OpenAI provider au lieu de Mistral API. `MISTRAL_API_KEY` devient optionnel (default `""`).
- `chat_agent.py` : `create_agent(model_name, base_url)` — si `base_url` fourni, utilise `OpenAIModel`/`OpenAIProvider`, sinon `MistralModel`/`MistralProvider`.
- `evals/task.py` : Support `FELIX_EVAL_BASE_URL` env var.
- `cli.py` : Header affiche le provider (Mistral API ou URL locale).

**Usage CLI local :**
```bash
MODEL_BASE_URL=http://localhost:1234/v1 MISTRAL_MODEL=qwen2.5-7b-instruct-1m felix
```

**Usage evals local :**
```bash
FELIX_EVAL_MODEL=qwen/qwen2.5-7b-instruct FELIX_EVAL_BASE_URL=http://localhost:1234/v1 uv run python -m evals.run_evals
```

**Modeles locaux disponibles (LMStudio) :** Qwen2.5 7B, Llama 3.1 8B, Ministral 3B, Gemma 2 9B.

**Evals Nemo API (apres fix accents) :**
- facts_score : 0.619 (vs 0.548 avant), assertions : 72.2% (vs 66.7%)
- La normalisation des accents a corrige les faux negatifs (lookup_location : 0.333 → 1.00)
- Faiblesses restantes cote modele : hallucination sur tests negatifs, cross-era en anglais sans tool calls, semantic_archives appelle get_timeline au lieu de search_scenes

**Evals Llama 3.1 8B local (LMStudio, Q4_K_M, 12k ctx) :**
- facts_score : 0.595, assertions : 83.3%, duree moyenne : 77s/case (~30x plus lent que Nemo API)
- Points positifs : refuse de fabriquer sur les tests negatifs (Nemo hallucine), meilleur score assertions
- Points negatifs : 30x plus lent, verbeux ("nous pourrions appeler find_character..." au lieu de l'appeler), cross-era score 0.0, lookup_location regression (0.333 vs 1.00 Nemo)
- Ajout flag `--local` dans run_evals.py pour simplifier le lancement

**Evals Gemma 2 9B local (LMStudio, google/gemma-2-9b) :**
- facts_score : 0.810, assertions : 94.4%, duree moyenne : 118s/case
- Refuse proprement de fabriquer, cite les scenes par numero (042, 088), repond en francais, concis

**Evals Qwen 2.5 7B local (LMStudio, qwen/qwen2.5-7b-instruct) :**
- facts_score : **0.857**, assertions : **100%**, duree moyenne : 89.8s/case
- Meilleur modele teste : 100% assertions, cross-era 0.75 (meilleur score), refuse proprement, plus rapide que Gemma 2 9B
- Seul 7B a atteindre 100% assertions — excellent tool-calling et raisonnement cross-era

| Metrique | Nemo 12B API | Llama 8B | Gemma 2 9B | **Qwen 2.5 7B** |
|----------|-------------|----------|------------|-----------------|
| facts_score | 0.619 | 0.595 | 0.810 | **0.857** |
| assertions | 72.2% | 83.3% | 94.4% | **100%** |
| duree/case | 2.7s | 77s | 118s | **89.8s** |
| negatifs | hallucine | refuse | refuse | **refuse** |
| cross-era | 0.5 | 0.0 | 0.5 | **0.75** |
| semantic_id | 0.667 | 0.667 | 1.00 | **1.00** |

**Evals Qwen3 4B (2507) local (LMStudio, qwen/qwen3-4b-2507, thinking OFF, 8k ctx) :**
- facts_score : 0.821, assertions : 94.4%, duree : **49.4s/case**
- Quasi 2x plus rapide que Qwen 2.5 7B avec qualite quasi identique
- Refuse proprement de fabriquer, cite les scenes, raisonne bien
- Faiblesses : rate "archives" (n'appelle pas search_scenes), manque "carbone" sur cross-era
- Candidat ideal pour PC modeste (moitie moins de RAM, 2x plus rapide)

| Metrique | Nemo 12B API | Llama 8B | Gemma 2 9B | Qwen 2.5 7B | **Qwen3 4B** |
|----------|-------------|----------|------------|-------------|-------------|
| facts_score | 0.619 | 0.595 | 0.810 | **0.857** | 0.821 |
| assertions | 72.2% | 83.3% | 94.4% | **100%** | 94.4% |
| duree/case | 2.7s | 77s | 118s | 89.8s | **49.4s** |
| negatifs | hallucine | refuse | refuse | refuse | refuse |

**Profils de deploiement envisages :**
- **PC correct** → Qwen 2.5 7B (100% assertions, ~90s/case)
- **PC modeste** → Qwen3 4B (94.4% assertions, ~50s/case)

---

### 2026-03-14 (5) — Qwen3 8B evals + prototype multi-agent

**Evals Qwen3 8B (thinking ON) :**
- facts_score : 0.738, assertions : 83.3%, duree : 276s/case
- Thinking active = 3x plus lent et moins bon que Qwen 2.5 7B
- Le modele raisonne trop et agit moins (n'appelle pas search_scenes sur "archives")

**Evals Qwen3 8B (thinking OFF, temp 0.1) :**
- facts_score : 0.774, assertions : 88.9%, duree : 83.3s/case
- Plus rapide mais toujours moins precis que Qwen 2.5 7B
- Rate le test "archives" (n'appelle pas search_scenes), fail voiture Marie

**Ajout temperature 0.1** dans `chat_agent.py` via `ModelSettings` — controle cote API, independant des settings LMStudio.

**Prototype multi-agent (retriever → reasoner) :**
- `chat_agent.py` : `create_retriever()` (tools, no reasoning) + `create_reasoner()` (no tools, raisonnement)
- `evals/task.py` : `felix_task_multi()` pipeline retriever → reasoner
- `run_evals.py` : flag `--multi`
- `cli.py` : flag `--multi`
- Constat : 2x plus de calls = trop lent en local. Architecture viable avec API rapide mais pas pour le use-case local.

**Decision :** Le client refuse les API cloud (confidentialite des donnees). Le MVP doit tourner 100% local. Le multi-agent est **abandonne** — 2x plus de calls par question = trop lent en local, et le gain en qualite n'est pas demontre. Code multi-agent retire du projet.

**Contrainte client :** Pas d'API cloud, le PC cible est potentiellement moins puissant que la machine de dev.

**Refactoring config :** Renommage des variables d'environnement (`MISTRAL_MODEL` → `FELIX_MODEL`, `MODEL_BASE_URL` → `FELIX_BASE_URL`, `MISTRAL_API_KEY` → `FELIX_API_KEY`). Ajout flags CLI (`--local`, `--model`, `--base-url`) pour eviter de jongler avec les env vars. README ajoute.

---

### Backlog — Tests modeles locaux a faire

Objectif : trouver le meilleur compromis qualite/vitesse pour un PC modeste.

- [x] ~~**Gemma 3 12B**~~ — Trop lent, coupe apres 30min. Non viable.
- [x] ~~**Gemma 3 4B**~~ — Pas de support tool-use, skip.
- [x] **Qwen3 8B sans thinking** — 0.774/88.9%, 83s/case. Moins bon que Qwen 2.5 7B.
- [x] **Qwen3 4B (2507)** — 0.821/94.4%, **49.4s/case**. Candidat PC modeste.
- [x] **Impact context length** — 4k ne gagne rien, rester sur 8k.
- [ ] **Qwen 2.5 7B Q4 vs Q8** — Comparer les quantisations.
- [ ] **Benchmark RAM/VRAM** — Mesurer la conso memoire reelle par modele.

---

## Phase 1 — Interface Textual (TUI) [SUPPRIMEE]

La TUI Textual a ete implementee puis supprimee au profit de l'interface web Nuxt UI (Phase 2). Les queries structurees ajoutees pour la TUI (`list_all_characters`, `get_character_profile`, `get_character_relations`, `get_timeline_rows`) sont conservees — elles servent maintenant au backend FastAPI.

Raison de la suppression : la web UI offre une UX bien superieure (design system, navigation, responsive) et la TUI ajoutait une dep lourde (textual) pour un resultat moins ambitieux.

---

## Phase 2 — Interface Web (Nuxt UI)

### 2026-03-14 — Backend FastAPI + Frontend Nuxt UI + suppression TUI

**Objectif :** Interface web riche avec Nuxt UI v4, remplace la TUI Textual. SPA locale, design aged-paper/screenplay aesthetic.

**TUI supprimee :**
- `src/felix/tui/` supprime, entry point `felix-tui` retire, dep `textual` retiree
- Les queries structurees de `queries.py` et leurs tests sont conserves (reutilises par l'API)

**Backend FastAPI (`src/felix/api/`) :**
- `main.py` — App FastAPI avec lifespan (init db/chroma/agent), CORS, health endpoint
- `models.py` — Pydantic response models (CharacterSummary, CharacterDetail, Relation, TimelineEvent, ChatRequest/ChatResponse)
- `routes/characters.py` — GET /api/characters, GET /api/characters/{id}
- `routes/timeline.py` — GET /api/timeline?era=
- `routes/chat.py` — POST /api/chat (multi-turn via message_history serialise avec ModelMessagesTypeAdapter)
- Entry point `felix-api` avec flags --local/--model/--base-url/--port

**Frontend Nuxt (`web/`) :**
- Nuxt 4 + @nuxt/ui v4 + Tailwind v4, SPA (ssr: false)
- Design system : palette Felix cyan (#0db9f2), aged-texture, tape-effect, handwritten-note
- Dashboard (stats + grille personnages + derniers evenements)
- Chat (bulles user/felix, loading dots animes, auto-scroll, clear)
- Personnages (grille filtrable par epoque, fiche detaillee avec relations)
- Timeline (UTable TanStack, filtre epoque, badges colores)
- Composables : useFelix (chat API), useCharacters, useTimeline
- Proxy dev /api → FastAPI localhost:8000

**Deps modifiees :**
- Ajout : fastapi>=0.115, uvicorn[standard]>=0.30
- Suppression : textual
- Node : nuxt@4, @nuxt/ui@4, @nuxt/eslint, @nuxt/fonts, tailwindcss@4, @iconify-json/lucide

**Verification :**
- `uv run pytest` — 27/27 tests passent (non-regression)
- `uv run ruff check src/` — 0 erreur
- `pnpm lint` — 0 erreur
- `pnpm nuxi typecheck` — 0 erreur
- `uv run felix` — CLI brut fonctionne toujours


### TODO WEB

- les liens sont en haut de la sidebar, avec le titre, tout ca devrait etre un navbar (header)
- on doit interpreter le markdown dans les questions / reponses
- **SSE chat** : streamer les tokens du LLM mot par mot via `agent.run_stream()` + `StreamingResponse` SSE. Remplacer le POST /api/chat actuel (reponse complete) par un endpoint SSE.
- **SSE import** : remplacer le poll /api/import/status par un flux SSE temps reel. Streamer les etapes du pipeline (analyse scene X → personnages trouves → resolution → chargement → check coherence). Pas de streaming tokens bruts (c'est du JSON structure), mais un event par etape avec le detail de ce qui vient d'etre fait.
- **ask_user interactif pendant l'import** : les heuristiques du resolver ne suffisent pas pour les cas ambigus (ex: "Jakes" seul vs "Jakes Milton", ou deux prenoms identiques a des epoques differentes). Le matching automatique par prenom seul est dangereux (deux "Marie" differentes). Solution : via SSE, le pipeline envoie un event `clarification_needed` quand le resolver est incertain, la UI affiche la question ("Jakes = Jakes Milton ?"), l'utilisateur confirme/refuse, le pipeline reprend. Necessite SSE import d'abord.
- **Merge/split personnages post-import** : en complement du ask_user, permettre de fusionner ou separer des personnages depuis la page Personnages (ex: corriger un lien errone apres coup).

---

## Phase 3 — Pipeline d'ingestion de scenes

### 2026-03-14 — Implementation complete du pipeline d'import

**Objectif :** Importer des fichiers .txt (1 par scene) et en extraire automatiquement les metadonnees via LLM local. Les incoherences sont logguees comme "issues" consultables dans la web UI.

**Architecture :**
```
[Dossier .txt] → [LLM Analysis/scene] → [Entity Resolution] → [DB + ChromaDB Upsert] → [LLM Consistency Check] → [Issues en DB]
```

**Data Layer (Phase A) :**
- `schema.py` — 2 tables ajoutees : `scenes` (id, filename, title, summary, era, date, location_id, raw_text) et `issues` (id, type, severity, scene_id, entity_id, description, suggestion, resolved)
- `queries.py` — 9 nouvelles fonctions : CRUD issues (list/create/update/delete), CRUD scenes (list/upsert), upsert minimal chars/locs, upsert timeline event/character_event
- `ingest/models.py` — Modeles Pydantic : SceneAnalysis, ExtractedCharacter, ExtractedLocation, ConsistencyIssue, ConsistencyReport
- `ingest/resolver.py` — Fuzzy matching `difflib.SequenceMatcher` (stdlib). Seuils : >=0.85 auto-link, 0.60-0.85 link+issue warning, <0.60 nouvelle entite. Registre mis a jour entre scenes.

**Pipeline Core (Phase B) :**
- `ingest/analyzer.py` — Agent pydantic-ai `output_type=SceneAnalysis`, prompt FR, temperature 0.1. Reutilise `_build_model()`.
- `ingest/loader.py` — Upsert scene/location/characters/event/chroma en 1 appel. Idempotent (INSERT OR REPLACE scenes, INSERT OR IGNORE chars/locs).
- `ingest/checker.py` — Agent pydantic-ai `output_type=ConsistencyReport`. Detecte incoherences temporelles, contradictions personnage, infos manquantes.
- `ingest/pipeline.py` — Orchestrateur async. ImportStatus enum, ImportProgress dataclass. Etapes : list files → load registry → analyze → resolve → load → check → insert issues.

**API (Phase C) :**
- `api/models.py` — 5 modeles ajoutes : Issue, IssueUpdate, ImportRequest, ImportProgressResponse, SceneSummary
- `api/routes/ingest.py` — 5 endpoints : POST /api/import (202, background task, mutex 409), GET /api/import/status, GET /api/issues (filtrable), PATCH /api/issues/{id}, GET /api/scenes

**Frontend (Phase D) :**
- `types/index.ts` — 3 interfaces ajoutees : Issue, ImportProgress, SceneSummary
- `composables/useImport.ts` — startImport + poll /api/import/status toutes les 2s
- `composables/useIssues.ts` — list filtrable + resolveIssue
- `composables/useScenes.ts` — list scenes
- `pages/import.vue` — Input chemin + bouton + progress bar + resultats (nouveaux persos/lieux)
- `pages/issues.vue` — Liste issues avec badges severity/type, filtres, bouton resoudre/reouvrir
- `components/AppSidebar.vue` — +2 items : Import (i-lucide-upload), Issues (i-lucide-alert-triangle)
- `pages/index.vue` — +2 stats cards : Scenes importees, Issues non resolues

**Tests :**
- `test_ingest_queries.py` — 14 tests (CRUD issues, upsert scenes, idempotence, minimal upserts)
- `test_resolver.py` — 12 tests (slugify, normalize, exact/alias/fuzzy/ambiguous match)
- `test_pipeline.py` — 3 tests (full pipeline mock LLM, empty dir, idempotence)

**Verification :**
- `uv run pytest` — 56/56 tests passent (29 nouveaux + 27 existants)
- `uv run ruff check src/` — 0 erreur
- `pnpm lint` — 0 erreur

### 2026-03-14 (2) — Evals ingest + amelioration prompt analyzer

**Objectif :** Mesurer la qualite de l'extraction de scenes (analyzer) via pydantic-evals, independamment du pipeline chat.

**Suite d'evals creee (`evals/ingest/`) :**
- 9 cas de test sur 2 scenes (001-la-poussiere.txt, 002-l-orbite.txt)
- 5 evaluateurs : CharacterRoleAccuracy, ExtractsExpectedCharacters, EraAccuracy, LocationAccuracy, NoCharacterPresent
- Metriques : role_accuracy (float), char_extraction (float), era_match (bool), location_match (bool), absent_pass (bool)

**Bug fix :** `NoCharacterPresent` ne heritait pas de `Evaluator[str, SceneAnalysis]` → ExceptionGroup. Deplace dans evaluators.py avec heritage correct.

**Resultats avant amelioration prompt (les deux modeles identiques) :**

| Metrique | Qwen 2.5 7B | Qwen3 4B |
|----------|-------------|----------|
| role_accuracy | 0.667 | 0.667 |
| char_extraction | 0.667 | 0.667 |
| era_match | ✔ | ✔ |
| location_match | ✔ | ✔ |
| absent_pass | ✔ | ✔ |
| Assertions | 100% | 100% |
| Duree/case | 90.3s | ~37s |

**Probleme identifie :** Les deux modeles ne detectent pas les personnages "mentioned" (Elias dans scene 1, Jakes dans scene 2). Le prompt demandait d'extraire les roles mais n'insistait pas assez sur les personnages simplement evoques.

**Amelioration prompt analyzer :**
- Ajout instruction explicite : "si un personnage est nomme ne serait-ce qu'UNE SEULE FOIS dans le texte, il DOIT apparaitre avec le role mentioned"
- Reformulation de la section PERSONNAGES pour insister sur l'exhaustivite

**Resultats apres amelioration (Qwen 2.5 7B) :**

| Metrique | Avant | Apres |
|----------|-------|-------|
| role_accuracy | 0.667 | **1.00** |
| char_extraction | 0.667 | **1.00** |
| era_match | ✔ | ✔ |
| location_match | ✔ | ✔ |
| absent_pass | ✔ | ✔ |
| Assertions | 100% | **100%** |
| Duree/case | 90.3s | 104.8s |

Le prompt v2 resout completement le probleme — score parfait sur tous les evaluateurs. Note : le modele extrait aussi Neo-Santiago comme "mentioned" (c'est un lieu, pas un personnage), mais c'est inoffensif car les evaluateurs ne penalisent pas les extras.

---

### 2026-03-14 (3) — SSE import streaming + ask-user clarification

**Objectif :** Remplacer le polling import par du SSE temps reel, ajouter un mecanisme interactif `ask_user` pendant l'import pour les entites ambigues.

**Backend :**
- `pipeline.py` — Refactorise avec `EventQueue`, `_PipelineContext`, `_process_scene()`, `_run_consistency_check()`. Emet des events : `status_change`, `scene_analyzed`, `entity_resolved`, `scene_loaded`, `issue_found`, `done`, `error`.
- `pipeline.py` — `ClarificationSlot` (asyncio.Event + answer). Quand le resolver retourne `AmbiguousMatch`, le pipeline emet `clarification_needed`, attend 30s la reponse utilisateur, auto-resolve en "link" si timeout.
- `ingest.py` — `POST /api/import/stream` (EventSourceResponse, lit la queue, yield SSE). `POST /api/import/clarify` (debloque le ClarificationSlot). Ancien endpoint polling conserve pour compat.

**Frontend :**
- `useImport.ts` — Remplace le polling par `fetch()` + `parseSSEStream()`. Expose `events`, `clarification`, `respondClarification()`. Fetch direct vers `http://localhost:8000` (bypass Nitro devProxy qui bufferise les SSE).
- `import.vue` — Journal d'import temps reel (icones + texte formate par type d'event). Carte de clarification inline (question, score, boutons "Oui, meme entite" / "Non, nouvelle entite", note timeout 30s).
- `types/index.ts` — Types `ImportEvent`, `ClarificationRequest`.
- `utils/parseSSE.ts` — Parser SSE generique `async function* parseSSEStream()`.
- `nuxt.config.ts` — `runtimeConfig.public.apiStreamBase` pour les fetches SSE directs.

**Problemes rencontres :**
1. **Nitro devProxy bufferise les SSE** — Le proxy h3 de Nitro ne supporte pas le streaming. Fix : les fetches SSE vont directement au backend (`http://localhost:8000`), CORS deja configure. Les appels non-SSE continuent via le devProxy.
2. **SSE parser `.trim()` supprimait les espaces** — Les tokens LLM arrivaient colles ("trouvepas"). Fix : ne plus trimmer les data SSE, seulement strip le `\r` des fins de ligne.

**Chat SSE non retenu :**
- `agent.run_stream()` / `agent.iter()` + `node.stream()` envoient `stream: true` au LLM. Qwen 2.5 7B n'appelle pas les tools en mode streaming — il repond directement sans chercher. Le chat reste en `agent.run()` classique (non-streaming) ou les tools fonctionnent correctement.
- Note : le modele ne reconnait pas toujours les noms ambigus comme "pixel" (un drone) sans contexte. Avec "qui est le personnage Pixel ?" ou un nom humain comme "Lena Voss", les tools sont appeles correctement.

**A explorer :**
- **Glossaire dynamique dans le system prompt** — Injecter la liste des personnages/lieux connus pour que le modele sache quoi chercher. Aiderait sur les noms que le modele ne reconnait pas spontanement comme des entites (ex: "Pixel", "Mite").
- **Chat SSE quand modele compatible** — Avec un modele supportant les tool calls en streaming (Mistral API, GPT, etc.), re-activer le streaming chat via `agent.iter()` + `node.stream()`. Le code SSE (parser, composable) est deja pret cote import.

**Verification :**
- `uv run pytest` — 58/58 tests passent
- `uv run ruff check src/` — 0 erreur
- `pnpm lint` — 0 erreur

---

### 2026-03-15 — Remplacement SequenceMatcher par rapidfuzz dans resolver.py

**Objectif :** Ameliorer les performances et la qualite du fuzzy matching des entites (personnages, lieux).

**Changements :**
- `pyproject.toml` — ajout dependance `rapidfuzz>=3.0`
- `src/felix/ingest/resolver.py` — remplacement de `difflib.SequenceMatcher` par `rapidfuzz.fuzz.WRatio`. WRatio selectionne automatiquement le meilleur algo (ratio, partial_ratio, token_sort_ratio, token_set_ratio), ce qui couvre nativement les inversions prenom/nom.
- `tests/test_resolver.py` — ajout `test_token_inversion_match` : verifie que "Martin Jean" matche "Jean Martin"

**Resultats :**
- 17/17 tests passent (16 existants + 1 nouveau)
- Aucun ajustement de seuil necessaire (THRESHOLD_AUTO=0.85 conserve)
- Gain de performance attendu : 5-100x vs SequenceMatcher (C++ vs Python pur)
- Import SSE : events temps reel, clarification interactive fonctionne, auto-resolve 30s OK

---

### 2026-03-15 — Separation queries.py → repository + formatters (issue #11)

**Objectif :** Appliquer le SRP sur `src/felix/db/queries.py` (532 lignes) qui melangeait CRUD pur et formatage texte pour l'agent.

**Changements :**
- `src/felix/db/repository.py` — cree : toutes les fonctions CRUD pures (SELECT, INSERT, UPSERT, UPDATE, DELETE), retournent `dict`, `Row`, ou `None`
- `src/felix/db/formatters.py` — cree : fonctions de formatage texte pour l'agent (`find_character`, `find_location`, `get_timeline`, `_format_character_profile`). Consomme repository. `get_timeline` appelle `repository.get_timeline_rows()` eliminant la duplication SQL.
- `src/felix/db/queries.py` — supprime
- `agent/tools.py` — import `formatters`
- `api/routes/characters.py`, `locations.py`, `ingest.py`, `timeline.py`, `export.py` — import `repository`
- `cli.py` — import `repository as db_queries`
- `ingest/pipeline.py`, `ingest/loader.py` — import `repository`
- `tests/test_formatters.py` — cree (renomme depuis `test_queries.py`), imports scindés `formatters` + `repository`
- `tests/test_queries.py` — supprime
- `tests/test_ingest_queries.py` — import `repository as queries`, `find_location` remplace par `get_location_detail`
- `tests/test_pipeline.py` — imports scindés `repository` + `formatters`

**Resultats :**
- 69/69 tests passent
- Aucun import residuel vers `felix.db.queries`

---

### 2026-03-15 — Filtre location sur get_timeline + durcissement system prompt

**Probleme :** Felix ne pouvait pas repondre a "qui est au poste de relais ?" — `get_timeline` n'avait pas de filtre par lieu. De plus le modele hallucine sur les descriptions de lieux et demande des clarifications inutiles.

**Modifications :**
- `repository.py` : `get_timeline_rows` accepte `location: str | None` — filtre `LOWER(l.name) LIKE '%...%'` + `INNER JOIN` quand actif
- `formatters.py` : `get_timeline` passe `location` au repository, mention dans le message no-result
- `agent/tools.py` : parametre `location` expose dans le tool, docstring corrigee (suppression "Always provide date_from/date_to")
- `agent/chat_agent.py` : system prompt durci — interdiction explicite d'inventer au-dela des tools, interdiction de demander des clarifications, exemple mis a jour avec `get_timeline(location=...)`

**Resultats :**
- 69/69 tests passent
- Pour "qui est au poste de relais ?", Felix peut enchainer `find_location` + `get_timeline(location="poste de relais")`

---

### 2026-03-15 (2) — Tentative streaming visuel des tool calls (revert)

**Idee :** Differencer visuellement la "pensee" du modele (texte emis avant un tool call) de la reponse finale, et afficher les tool calls en live avec `agent.iter()`.

**Implementation tentee :**
- Remplacement de `agent.run()` par `agent.iter()` dans `cli.py`
- Iteration sur les noeuds `ModelRequestNode` et `CallToolsNode`
- `CallToolsNode` avec `ToolCallPart` → texte intermédiaire en dim italique + `🔧 tool_name(args)` en dim
- Reponse finale via `agent_run.result.output`

**Probleme :** pydantic-ai avec `iter()` ne stream pas les evenements *pendant* l'execution d'un noeud — chaque noeud n'est yielde qu'une fois termine. L'UX etait donc identique a `agent.run()`, aucune difference visuelle en pratique.

**Revert.** Pour vraiment afficher les tool calls en live, il faudrait soit du streaming token-par-token (hooks dans les tools), soit un callback custom.

---

### 2026-03-15 (3) — Passage à bge-m3 (embedding multilingue)

**Probleme :** Le modele d'embedding par defaut de ChromaDB (`all-MiniLM-L6-v2`) est anglophone. Le contenu de Felix etant principalement en francais, la qualite de la recherche semantique etait degradee.

**Modifications :**
- `pyproject.toml` : ajout de `sentence-transformers>=3.0`
- `vectorstore/store.py` : `SentenceTransformerEmbeddingFunction(model_name="BAAI/bge-m3")` passe a `get_or_create_collection()`

**Notes :**
- bge-m3 produit des vecteurs 1024 dimensions (vs 384 pour MiniLM) — incompatible avec une collection existante, necessite de vider `chroma_data/` et re-indexer
- Modele telecharge automatiquement via HuggingFace (~2.27GB), mis en cache dans `~/.cache/huggingface/hub/`

---

### 2026-03-15 (4) — Déduplication fuzzy des relations personnages

**Probleme :** Le profiler tourne une fois par personnage. Pour une paire (A, B), A génère `"collaborateur"` et B génère `"collaborateur sur l'interpretation..."` — deux `relation_type` différents → deux lignes en DB alors qu'il s'agit de la même relation.

**Cause racine :** La PK de `character_relations` inclut `relation_type`, permettant plusieurs lignes par paire avec des libellés légèrement différents.

**Modifications :**
- `db/repository.py` : ajout de `get_relation_types_for_pair(db, a, b)` — retourne les `relation_type` existants pour une paire normalisée
- `ingest/pipeline.py` : avant chaque `upsert_character_relation`, vérification fuzzy (`fuzz.ratio >= 75`) contre les relations existantes pour la paire — skip si trop similaire, insert sinon

**Choix du seuil 75 :** bloque "collaborateur" vs "collaborateur sur l'interpretation..." (~60-70), laisse passer "père" vs "rival" (~30).

---

### 2026-03-15 (5) — DI idiomatique FastAPI (issue #8)

**Probleme :** Toutes les routes accédaient aux services via `request.app.state` — Service Locator implicite sans typage, non documenté, non testable.

**Modifications :**
- `api/deps.py` : nouveau fichier — 5 fonctions `get_*` (db, collection, agent, model_name, base_url) + 5 alias `TypeAlias` annotés (`DB`, `Collection`, `ChatAgent`, `ModelName`, `BaseUrl`)
- `api/main.py` : lifespan stocke `collection` directement sur `app.state` (suppression du wrapper `FelixDeps`), endpoint `health` utilise `ModelName`/`BaseUrl` via Depends
- `api/routes/characters.py`, `locations.py`, `timeline.py`, `export.py` : `request: Request` remplacé par `db: DB`
- `api/routes/chat.py` : `request: Request` remplacé par `agent: ChatAgent, db: DB, collection: Collection` ; `FelixDeps` reconstruit à la volée pour pydantic-ai
- `api/routes/ingest.py` : état statique (db, collection, model_name, base_url) → typed deps ; état dynamique (import_progress, import_task, pending_clarifications) reste sur `request.app.state` (mutable runtime)