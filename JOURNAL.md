# Journal de developpement — Felix

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
FELIX_EVAL_MODEL=qwen2.5-7b-instruct-1m FELIX_EVAL_BASE_URL=http://localhost:1234/v1 uv run python -m evals.run_evals
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

**Evals Qwen 2.5 7B local (LMStudio, qwen2.5-7b-instruct-1m) :**
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
