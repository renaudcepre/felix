# Journal de developpement — Felix

## Vision produit — discussion avec Felix (scenariste) — 2026-03-25

Trois couches distinctes émergent :

1. **World Model** (existant) — graphe de connaissances, source de vérité sur l'univers
   du scénario
2. **Notes / Idées** (à construire) — espace de réflexion non validé, croisable entre
   notes et avec le world model
3. **Écriture** (futur) — rédaction du scénario lui-même, exercice distinct de "décrire
   le monde"

**Concept d'arène** : notion plus riche que "location" — contexte thématique et
spatial (ex: "la piraterie" comme arène avec ses codes et personnages-types). A
modéliser quand on sera prêt.

Priorités : notes = next step naturel (low effort, high value). Écriture assistée = plan
long terme.

## Passage full anglais — 2026-03-25

Traduction de tout le contenu FR → EN : 23 scènes (data + fixtures), seed data (graph +
vectorstore), messages UI, expected values des evals, termes éphémères physiques. Motivé
par le franglais (profils EN vs scènes FR) qui cassait le consistency checker et rendait
les evals fragiles.

Scores post-traduction : 168/199 pipeline (+11 grâce aux keywords corrigés). Groups
11/11 (100%).

## Page Groupes (frontend + API) — 2026-03-25

5 endpoints API (list, create, detail, add/remove member). Frontend : liste, création,
page détail avec gestion des membres. `find_character` enrichi pour retourner les
groupes d'appartenance au chatbot.

## Consistency checker profil — 2026-03-23/25

Bouton "Vérifier" pour checker les modifications de profil contre les scènes. Approche
hybride : pré-matching textuel (n-grammes) + LLM pour les cas sans evidence.

Itérations successives :

- Diff only (ne checker que ce qui a changé, pas tout le profil)
- Suppression de `missing_evidence` — seules les contradictions comptent (le scénariste
  peut ajouter ce qu'il veut)
- `character_name` dans le payload pour éviter la confusion entre personnages
- Limites du 7B : flag des non-contradictions malgré le prompt. Dépend du passage full
  anglais pour fonctionner correctement.

## Seuil bas dedup relations — 2026-03-25

Score fuzzy < 30 → `keep_both` direct sans LLM ni clarification. "messagère" vs "
Tisserand of the Vermeil Order" (score 15) ne pose plus la question.

## Code review + refactoring — 2026-03-23

**Repository split** : `repository.py` (1021 lignes) découpé en 7 modules domaine dans
`graph/repositories/`.

**TypedDict** : 20 types pour les retours repository, `cast()` no-op runtime, zéro coût.

**Pipeline refactor** : `run_import_pipeline` décomposé en 5 sous-fonctions.
`_PipelineContext` enrichi avec `model_name`/`base_url`/`enrich_profiles` pour
simplifier les signatures.

**Quick wins** : `datetime.now(UTC)`, `Literal` pour ConsistencyIssue, embedding model
unifié, `normalize()` centralisée, `build_model` dans `llm.py`, fonctions publiques dans
`resolution.py`.

## Expansion evals + tags — 2026-03-23

+70 cas de test (129 → 199). Système de tags cross-suites (`--tag dates`,
`--tag profiling`).

## Groups/Factions — 2026-03-20

Nœud `:Group` + `MEMBER_OF`. Les collectifs (drones, pillards) sont distincts des
personnages individuels. `character_type: Literal["individual", "group"]` dans
l'extraction.

## Narrative beats pour attribution — 2026-03-18

Extraction `subject → action → object` par scène, puis filtrage par personnage avant le
profiler. Résout les erreurs d'attribution flaky avec le 7B.

## Décomposition pipeline.py — 2026-03-19

`pipeline.py` (903 lignes) séparé en `resolution.py`, `orchestrator.py`, `pipeline.py`.
Responsabilités claires.

## Dedup relations : fuzzy + LLM + clarification — 2026-03-19/21

Pipeline 3 étages : ≥90 auto-merge, [55-90) LLM, <55 keep_both. Ajout "unsure" →
clarification utilisateur.

## Segmentation narrative — 2026-03-17

Découpage sémantique en chunks overlappants pour les fichiers longs. Liaison
`NEXT_CHUNK` dans le graphe. Idempotence re-import.

## Migration Neo4j — 2026-03-17

SQLite + Kuzu → Neo4j comme store unique. Cypher partout, async natif. Docker-compose
avec volume persistant.

## Pipeline incrémental — 2026-03-15

Check + profiling après chaque scène (plus en batch). Issues écrites en DB
immédiatement.

## Refonte evals — 2026-03-15

Exécution parallèle, Together AI comme provider cloud, 3 suites (
pipeline/ingest/chatbot), CLI unifiée. `LLMJudge` pour les cas causaux,
`RefusesToFabricate` pour les négatifs.

## Phase 0 — POC CLI — 2026-03-14

pydantic-ai + Mistral Nemo 12B + SQLite + ChromaDB. Validation que le modèle appelle les
tools correctement. Pattern `find_character` en 1 appel (le 12B ne suivait pas list→get
en 2 étapes). Support modèles locaux via LMStudio.

Leçons : le mix FR/EN dans les prompts est trop ambigu pour les petits modèles.
`TYPE_CHECKING` incompatible avec l'introspection runtime de pydantic-ai.
