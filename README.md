# Felix — Screenplay Continuity Assistant

Assistant de continuite pour scenaristes. Felix repond a des questions sur les personnages, lieux, evenements et scenes d'un thriller multi-epoques, en s'appuyant sur une bible de scenario (SQLite + ChromaDB).

## Stack

- **pydantic-ai** — orchestration LLM + tool-calling
- **SQLite** (aiosqlite) — donnees structurees (personnages, lieux, timeline)
- **ChromaDB** — recherche semantique sur les scenes
- **rich** — CLI interactive

## Installation

```bash
uv sync
```

## Usage

### Local (LMStudio)

Par defaut Felix pointe sur `http://localhost:1234/v1` avec Qwen 2.5 7B.

```bash
# Modele par defaut
uv run felix

# Choisir un modele
uv run felix --model qwen/qwen3-4b-2507

# URL custom (autre machine)
uv run felix --base-url http://192.168.1.10:1234/v1
```

### API Mistral

```bash
# Necessite FLX_LLM_BASE_URL="" et FLX_LLM_API_KEY dans .env
uv run felix --base-url "" --model mistral-small-latest
```

## Dev (just)

```bash
just dev-up   # API (hot reload, port 8000) + frontend Nuxt (port 3000)
just api      # API seule
just web      # frontend seul
just db-clean # supprime DB + ChromaDB
just db-archive # archive puis nettoie
```

## Evals

```bash
# Local (LMStudio)
uv run python -m evals.run_evals --local
uv run python -m evals.run_evals --local --model qwen/qwen3-4b-2507

# API Mistral
uv run python -m evals.run_evals
```

## Tests

```bash
uv run pytest
```

## Modeles testes

| Modele | facts_score | assertions | duree/case | negatifs |
|--------|-------------|------------|------------|----------|
| **Qwen 2.5 7B** | **0.857** | **100%** | 89.8s | refuse |
| Qwen3 4B | 0.821 | 94.4% | 49.4s | refuse |
| Gemma 2 9B | 0.810 | 94.4% | 118s | refuse |
| Qwen3 8B | 0.774 | 88.9% | 83.3s | refuse |
| Nemo 12B API | 0.619 | 72.2% | 2.7s | hallucine |
| Llama 3.1 8B | 0.595 | 83.3% | 77s | refuse |

**Recommandation :**
- PC correct → Qwen 2.5 7B (100% assertions, ~90s)
- PC modeste → Qwen3 4B (94.4% assertions, ~50s)

## Configuration

Variables d'environnement (ou `.env`) :

| Variable | Description | Default |
|----------|-------------|---------|
| `FLX_LLM_MODEL` | Nom du modele | `qwen/qwen2.5-7b-instruct` |
| `FLX_LLM_BASE_URL` | URL API OpenAI-compatible | `http://localhost:1234/v1` |
| `FLX_LLM_API_KEY` | Cle API | _(vide)_ |
