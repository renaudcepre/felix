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
