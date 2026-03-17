# Felix — Screenplay Continuity Assistant

Felix is an AI-powered continuity assistant for multi-era screenplays. Drop your scenes as plain text files; Felix extracts characters, locations, and dates, builds a knowledge graph, detects narrative inconsistencies, and answers continuity questions in natural language.

---

## Architecture

```
scenes/          ──► Ingest Pipeline ──► Neo4j (graph)
(plain text)                         └──► ChromaDB (vectors)
                                              │
                                    FastAPI REST API
                                              │
                                    ┌─────────┴──────────┐
                                  Nuxt UI           Felix CLI
                                (web/port 3000)  (terminal chat)
```

| Layer | Technology |
|---|---|
| Graph DB | Neo4j 5 (async, Bolt) |
| Vector store | ChromaDB + sentence-transformers |
| LLM agents | pydantic-ai (Mistral API / Together AI / LM Studio) |
| API | FastAPI + uvicorn |
| Frontend | Nuxt 3 + Nuxt UI |
| Runtime | Python 3.12, uv |

---

## Graph Schema

```
(Character)-[:PRESENT_IN {role}]────────►(Scene)
(Character)-[:RELATED_TO {relation_type}]►(Character)
(Character)-[:PARTICIPATES_IN {role}]───►(TimelineEvent)
(Scene)────[:AT_LOCATION]───────────────►(Location)
(Scene)────[:HAS_ISSUE]─────────────────►(Issue)
(TimelineEvent)─[:AT_LOCATION]──────────►(Location)
(TimelineEvent)─[:FROM_SCENE]───────────►(Scene)
```

**Key node properties:**
- `Character` — `id` (slug), `name`, `aliases[]`, `era`, `background`, `arc`, `traits`, `physical`, `status`
- `Scene` — `id` (derived from filename stem), `title`, `date`, `era`, `summary`, `raw_text`, `filename`
- `Issue` — `id` (deterministic for bilocalization: `biloc-{char}-{s1}-{s2}`), `type`, `severity`, `description`, `suggestion`, `resolved`

---

## Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Docker](https://www.docker.com/) — for Neo4j
- [pnpm](https://pnpm.io/) — for the frontend (optional)

### 1. Start Neo4j

```bash
docker compose up -d
```

Neo4j runs on `bolt://localhost:7687` (user: `neo4j`, password: `felixpassword`).
Neo4j Browser: `http://localhost:7474`

### 2. Configure environment

Create a `.env` file at the project root:

```dotenv
# Mistral API
FLX_LLM_API_KEY=your_mistral_api_key

# or Together AI
TOGETHER_API_KEY=your_together_key
FLX_LLM_BASE_URL=https://api.together.xyz/v1
FLX_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct-Turbo

# or LM Studio (auto-detected at localhost:1234)
# FLX_LLM_BASE_URL=http://localhost:1234/v1
# FLX_LLM_MODEL=qwen2.5-7b-instruct
```

All settings use the `FLX_` prefix. See `src/felix/config.py` for the full list.

| Variable | Description | Default |
|---|---|---|
| `FLX_LLM_MODEL` | Model name | `Qwen/Qwen2.5-7B-Instruct-Turbo` |
| `FLX_LLM_BASE_URL` | OpenAI-compatible base URL | `https://api.together.xyz/v1` |
| `FLX_LLM_API_KEY` | Mistral API key | _(empty)_ |
| `TOGETHER_API_KEY` | Together AI key | _(empty)_ |
| `FLX_NEO4J_URI` | Neo4j Bolt URI | `bolt://localhost:7687` |
| `FLX_NEO4J_USER` | Neo4j username | `neo4j` |
| `FLX_NEO4J_PASSWORD` | Neo4j password | `felixpassword` |
| `FLX_CHROMA_PATH` | ChromaDB data directory | `chroma_data` |
| `LOGFIRE_TOKEN` | Logfire observability token | _(empty)_ |

### 3. Install and run

```bash
uv sync
just dev-up     # API (port 8000) + Nuxt frontend (port 3000)
```

---

## Ingest Pipeline

Each scene file is processed through four async stages:

```
1. analyze   LLM extracts characters, location, date, era, summary from raw text
2. load      Fuzzy-match entities against the existing graph (rapidfuzz + MERGE),
             write Character / Scene / Location nodes to Neo4j,
             embed scene text into ChromaDB
3. check     timeline_checker + narrative_checker agents scan for inconsistencies
             → Issue nodes (timeline, narrative, contradiction)
             + Cypher bilocalization check (same date, different location)
4. profile   Profiler agent writes / patches character background for this scene;
             patch agent merges cross-scene info into a coherent profile
```

Re-importing a scene is **idempotent**: existing Scene nodes are deleted and rewritten; issues for those scenes are pruned before recreation.

To import scenes via the API:

```bash
curl -X POST http://localhost:8000/api/ingest \
     -F "files=@scenes/01_signal.txt" \
     -F "files=@scenes/02_rapport.txt"
```

---

## Chat Agent

Felix answers continuity questions in French. It uses four tools:

| Tool | What it does |
|---|---|
| `find_character(name)` | Character profile, aliases, arc, physical description |
| `find_location(name)` | Location description and associated events |
| `get_timeline(location?, date_from?, date_to?)` | Timeline events with optional filters |
| `search_scenes(query)` | Semantic similarity search over scene text (ChromaDB) |

The agent **only reports what tools return** — it refuses to invent facts.

```bash
felix                                    # interactive chat (uses .env settings)
felix --model mistral-small-latest
felix --base-url http://localhost:1234/v1 --model qwen2.5-7b-instruct
```

---

## API Routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Model + provider status |
| `GET` | `/api/characters` | List all characters |
| `GET` | `/api/characters/{id}` | Character detail + scene fragments |
| `PATCH` | `/api/characters/{id}` | Update character profile |
| `GET` | `/api/locations` | List all locations |
| `GET` | `/api/timeline` | Timeline events (filterable by date / era / location) |
| `POST` | `/api/chat` | Chat with the agent |
| `POST` | `/api/ingest` | Import scene files (multipart) |
| `GET` | `/api/export` | Export full graph as JSON |

---

## Task Runner

```bash
just dev-up        # API (hot reload) + frontend in parallel
just api           # API only
just web           # Nuxt frontend only
just export        # Export graph to exports/<timestamp>.json
just db-clean      # Wipe all data (Neo4j + ChromaDB)
just db-archive    # Archive ChromaDB snapshot then wipe
just evals         # Run all eval suites (auto-detects provider)
just evals --suite pipeline --mistral
just evals --suite pipeline --list
just evals --suite pipeline --case character_extraction --together
```

---

## Evals

Felix uses [pydantic-evals](https://ai.pydantic.dev/evals/) for LLM evaluation — not pytest.
All suites run in a **single asyncio event loop** to avoid httpx connection pool bleeding between pipeline runs.

### Suites

| Suite | Cases | Story | What it tests |
|---|---|---|---|
| `pipeline` | 34 | Helios (7 scenes) | Full ingest pipeline: extraction, profiling, relations, consistency, timeline |
| `pipeline-convoi` | 12 | Convoi (3 scenes) | Full ingest pipeline + bilocalization dedup regression |
| `ingest` | 17 | Mixed | Scene analyzer LLM in isolation (roles, era, location, negatives) |
| `chatbot` | 26 | WWII thriller | Chat agent: lookup, coherence, causal chains, alias resolution, negatives |

### Running evals

```bash
just evals                                        # all suites, auto-detect provider
just evals --suite pipeline --mistral             # Mistral API
just evals --suite pipeline-convoi --together     # Together AI
just evals --suite ingest --local                 # LM Studio

just evals --suite pipeline --list                # list all cases
just evals --suite pipeline --case character_extraction --mistral   # single case

just evals --suite pipeline --history             # show run history
just evals --suite pipeline --diff                # compare last two runs
```

Results are written to `evals/results/<suite>_<timestamp>/` (one `.md` per case) and appended to `evals/results/history.jsonl`.

### Fixture isolation

```
evals/fixtures/
  helios/     ← 7 scenes (Helios story)
  convoi/     ← 3 scenes (Convoi story, copied from data/scenes/)
```

Each pipeline suite targets its own subdirectory. The Neo4j DB is wiped at pipeline init (`MATCH (n) DETACH DELETE n`) so suites never interfere.

---

## Development

### Tests

```bash
uv run pytest               # all tests
uv run pytest tests/test_pipeline.py -v
```

Tests connect to a real Neo4j instance at `bolt://localhost:7687` (the same Docker instance used for development) — no mocking.

### Linting

```bash
uv run ruff check src/ evals/ tests/
uv run ruff format src/ evals/ tests/
```

### Graph exploration

Open `http://localhost:7474`. Useful queries:

```cypher
// Graph overview (hide Issue nodes)
MATCH p=()-[r]->() WHERE none(n IN nodes(p) WHERE n:Issue) RETURN p LIMIT 100

// Characters and their scenes
MATCH (c:Character)-[r:PRESENT_IN]->(s:Scene) RETURN c, r, s

// Open issues by type
MATCH (s:Scene)-[:HAS_ISSUE]->(i:Issue)
WHERE i.resolved = false
RETURN i.type, count(i) AS n ORDER BY n DESC

// Bilocalization issues
MATCH (i:Issue {type: "bilocalization"}) RETURN i.description, i.entity_id
```
