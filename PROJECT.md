# 🎬 Screenplay Assistant — Design Document

**Status:** Draft v0.7
**Purpose:** Local AI-powered continuity & bible management tool for screenwriters.
**Constraint:** 100% local, no cloud dependency.

---

## 1. Problem

Writing a complex multi-era polar (thriller) requires tracking characters, timelines, locations, and events across potentially hundreds of scenes. Human memory fails. Spreadsheets don't scale. The writer needs a tireless continuity supervisor — not a co-writer.

**Core principle:** The system never modifies the writer's text. It reads, analyzes, and reports. The writer stays in full control.

---

## 2. Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| LLM serving | LM Studio (host) | GUI for non-tech user, OpenAI-compatible API on localhost:1234 |
| Model target | Qwen3 8B Q4_K_M (16GB RAM) or 14B (32GB RAM) | Best structured reasoning at small size |
| Embeddings | nomic-embed-text (via LM Studio) | Local, fast, good quality |
| Agent framework | Pydantic AI | Typed tools, OpenAI-compatible, async |
| Structured storage | SQLite | Single file, no server, relational queries for cross-entity lookups |
| Vector store | ChromaDB | Lightweight, local, semantic search on scene prose |
| Backend | FastAPI | Obvious fit with Pydantic AI |
| Frontend | Vanilla JS + HTML/CSS | No build step, no Node dependency |
| Packaging | Docker Compose (API + ChromaDB) | LM Studio stays on host (needs GPU) |

---

## 3. Data Architecture

### 3.1 What stays OUT of RAG (SQLite, direct lookup)

These are deterministic lookups. The agent calls a tool to fetch exact records by ID. No embedding, no similarity search. All structured data lives in a single local SQLite database.

- **Characters** — name, aliases, physical description, relationships, era, arc, scene appearances
- **Timeline events** — date, description, characters involved, location, scene_id
- **Locations** — name, era, description, associated characters
- **Relations** — character↔event, character↔scene, character↔location links enable cross-queries ("all events involving Marie AND Lyon in 1942")

SQLite is still 100% local (single file, no server), supports relational queries natively, and avoids the pain of parsing dozens of JSON files for cross-entity lookups.

### 3.2 What goes IN the RAG (ChromaDB, semantic search)

These need fuzzy retrieval. The writer asks "find scenes where someone mentions the missing letter" — that's semantic, not a key lookup.

- **Scene drafts** — actual prose, chunked by scene, embedded with metadata. Metadata uses boolean keys per character present (e.g. `char_marie: true`, `char_pierre: true`) instead of comma-separated strings, because ChromaDB's `where` clause handles booleans reliably but struggles with substring matching in strings. Also includes `scene_id`, `era`, `location_id`.

### 3.3 Diagram

```
┌─────────────────────────────────────────┐
│            Agent receives task           │
├───────────────────┬─────────────────────┤
│  Structured       │   Semantic (RAG)    │
│  (SQLite)         │   (ChromaDB)        │
├───────────────────┼─────────────────────┤
│  characters       │  scenes collection  │
│  timeline_events  │                     │
│  locations        │                     │
│  relations        │                     │
└───────────────────┴─────────────────────┘
        ▲                    ▲
        │                    │
        └── tools (direct) ──┴── tools (search) ──── Agent
```

---

## 4. Agents

### 4.1 Scene Analyzer

**Used during:** Scene import flow.
**Input:** Raw scene text (plain text).
**Output:** Coherence report + proposed structured metadata for the writer to review.

**Step 1 — Extract metadata:** Characters present, date/era, location, key plot points.
**Step 2 — Check coherence:** Using the same tools as the Chat Agent, cross-reference the extracted metadata against the existing bible. Flag contradictions (timeline conflicts, character inconsistencies, location issues).
**Step 3 — Report:** Present the coherence report + proposed metadata to the writer. He reviews, adjusts, confirms.

**Note:** This agent never writes to the bible directly. It checks, proposes, the writer decides.

### 4.2 Chat Agent

**Used during:** Chat queries.
**Input:** Natural language question from the writer.
**Output:** Answer based on the bible + RAG, streamed.
**Tools available:** All structured lookups + semantic search (see section 5).

The chat agent replaces the need for dedicated "Timeline Guardian" or "Character Consistency Checker" agents. The writer just asks:
- "Is it coherent if Benoit meets Sarah in 1928?" → agent fetches both character profiles + 1920s timeline events, reasons about it
- "Where was Marie in March 1942?" → agent queries timeline filtered by era + character
- "Who knows about the letter at this point?" → agent searches scenes via RAG + checks character profiles
- "List all contradictions in the 1940s timeline" → agent loads full era timeline, checks for overlaps

The quality of the answers depends on the quality of the bible. Since the writer maintains it manually, the data is reliable — the model just needs to retrieve and reason, not generate knowledge.

---

## 5. Tools (Pydantic AI)

All tools below are available to both the **Chat Agent** and the **Scene Analyzer**. The model decides which tools to call based on the task.

### 5.1 Structured lookups

| Tool | Args | Returns |
|------|------|---------|
| `list_characters` | — | List of character names + IDs |
| `get_character` | id: str | Full character profile or None |
| `list_locations` | — | List of location names + IDs |
| `get_location` | id: str | Location details |
| `get_timeline` | era: str (optional), date_from: str (optional), date_to: str (optional) | Filtered list of timeline events. Date range required to avoid context blowup. |

### 5.2 Semantic search (RAG)

| Tool | Args | Returns |
|------|------|---------|
| `search_scenes` | query: str, era: str (optional), characters: list[str] (optional) | Relevant scene chunks with metadata |

### 5.3 No write-back tools

Neither agent has write access to the bible at the tool level. They query, they never modify. Bible modifications happen through two paths only:
- **Manual edits** by the writer via the Bible Manager UI → API CRUD endpoints → SQLite
- **Scene import** flow: Scene Analyzer proposes metadata (or a diff on re-import) → writer reviews and confirms via the UI → API commits to SQLite + ChromaDB

---

## 6. Ingestion Pipeline

Re-ingestion is triggered by **scene lifecycle events**, not batch jobs.

### 6.1 New scene

```
Writer imports scene_042 (plain text)
       │
       ▼
Scene Analyzer extracts metadata
       │
       ▼
Checks coherence against existing bible:
  - Timeline conflicts? (character in two places at once, anachronisms)
  - Character inconsistencies? (physical traits, relationships, knowledge)
  - Location issues? (places that don't exist in this era)
       │
       ▼
Presents to writer:
  ⚠ Coherence issues found:
    - "Marie is already in Paris on 1942-03-15 (scene_038)"
  ✚ Proposed metadata:
    - Characters detected: [Marie, Pierre]
    - Events: [{date: 1942-03-15, description: "Meeting at safe house"}]
    - Location: Lyon safe house
       │
       ▼
Writer reviews, resolves issues, adjusts metadata, confirms
       │
       ├──▶ Inserts into SQLite (characters, events, locations, relations)
       │
       ▼
Embed scene_042 into ChromaDB
  metadata: {scene_id: "042", era: "1940s", char_marie: true, char_pierre: true}
       │
       ▼
Ready for chat queries
```

### 6.2 Modified scene (re-import)

```
Writer re-imports scene_042 (updated text)
       │
       ▼
Scene Analyzer extracts NEW metadata
       │
       ▼
Compares with OLD metadata (from SQLite):
  - Characters added? removed?
  - Events changed? deleted?
  - Location changed?
       │
       ▼
Presents DIFF to writer:
  ✚ Added: Pierre now present
  ✖ Removed: Marie no longer in scene
  ~ Changed: date shifted from March 15 to March 20
       │
       ▼
Writer reviews diff, adjusts, confirms
       │
       ├──▶ Updates SQLite (add/remove relations, update events)
       │
       ▼
Re-embed scene_042 into ChromaDB
  (delete old chunks first, embed new version with updated metadata)
```

### 6.3 Manual bible edit

Writer edits a character/event/location via the Bible Manager → SQLite updated directly, no re-ingestion needed. The chat agent will see the changes immediately on next query.

### 6.4 Never re-embed everything

Incremental updates only, keyed by scene_id.

---

## 7. Frontend

### 7.1 Three areas

The writer spends most of his time in the **Bible Manager** — maintaining his screenplay's source of truth. The **Chat** is where he queries and checks coherence.

| Area | Purpose |
|------|---------|
| **Bible Manager** (main) | Full CRUD on characters (create/edit profile sheets, physical descriptions, relationships, arcs), timeline events (add/edit/reorder/delete events, assign to eras), and locations. This is the writer's primary workspace — he maintains the bible by hand, the way he wants it. |
| **Scene import** | Drop zone or textarea to add finished scenes (plain text). Triggers Scene Analyzer → checks coherence against existing bible (flags contradictions) → proposes metadata to add → writer reviews issues, adjusts, confirms. |
| **Chat** | Natural language query interface. The writer asks coherence questions ("is it coherent if Benoit meets Sarah in 1928?", "where was Marie in March 1942?", "who knows about the letter at this point in the story?"). The system uses tools to query the bible + RAG and answers. |

### 7.2 Key UX decisions

- **Bible Manager is manual and direct** — the writer is the authority. No AI in the loop when he edits a character sheet or adds a date. The data is exactly what he puts in.
- **Scene import is AI-assisted** — the model checks coherence first, then proposes metadata. Always with writer review before commit.
- **Chat is read-only** — queries the data but never modifies it. No risk of the model corrupting the bible through a question.
- **Websocket for streaming** — local models are slow, chat responses stream token by token. Scene import shows step-by-step progress.
- **Warm, writerly aesthetic** — not a dev tool. Dark mode optional.
- **Timeline visualization** — in the bible manager, a horizontal bar per era with events plotted. Editable inline (click to edit, drag to reorder).

---

## 8. API

```
# Chat (read-only queries on the bible + RAG)
WS     /ws/chat                    → websocket for streaming chat (query + response)

# Scene management
POST   /scenes/                    → import scene (plain text), triggers Scene Analyzer
POST   /scenes/{id}/confirm        → confirm extracted metadata, commit to bible + RAG
GET    /scenes/{id}                → scene content + metadata

# Bible — Characters (full CRUD)
GET    /characters/                → list all characters
POST   /characters/                → create character profile
GET    /characters/{id}            → full character profile
PUT    /characters/{id}            → update character profile
DELETE /characters/{id}            → delete character

# Bible — Timeline (full CRUD)
GET    /timeline/                  → all events (filterable by ?era=, ?date_from=, ?date_to=)
POST   /timeline/                  → create event
PUT    /timeline/{id}              → update event
DELETE /timeline/{id}              → delete event

# Bible — Locations (full CRUD)
GET    /locations/                 → all locations
POST   /locations/                 → create location
PUT    /locations/{id}             → update location
DELETE /locations/{id}             → delete location
```

**Note:** All entities use UUIDs as primary keys internally. Display names are stored as attributes, not identifiers. This means renaming "Marie Dupont" to "Marie Clairet" changes a single field — no cascade update needed across events, scenes, or relations.

---

## 9. Docker Compose

```yaml
services:
  api:
    build: .
    ports: ["8000:8000"]
    volumes:
      - ./data:/data          # SQLite DB + scene files
    environment:
      - LLM_BASE_URL=http://host.docker.internal:1234/v1
      - LLM_MODEL=qwen3-8b
      - CHROMA_HOST=chroma

  chroma:
    image: chromadb/chroma
    volumes:
      - ./chroma_data:/chroma/chroma
```

LM Studio stays on the host machine (needs direct GPU/Metal access). API container reaches it via `host.docker.internal`.

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Small model hallucinating inconsistencies that don't exist | All findings are presented as suggestions for review, never auto-applied. Writer is final judge. |
| Poor tool calling with small models (loops, forgotten calls, hallucinated results) | Keep tool descriptions extremely directive (not just descriptive). Include a canonical few-shot example in the system prompt showing the expected step-by-step reasoning: list → get → reason. Add `list_*` tools so the model discovers valid IDs before calling `get_*`. Fallback: prompt for JSON output + Pydantic parsing if tool calling is too unreliable. |
| Context window blowup on broad queries | Tool returns must enforce token limits. `get_timeline` requires date range, not just an era (an era with 200 events would kill the context). Paginate results, return counts first so the model can narrow its query. |
| Scene modification diff (character removed, event changed) | On re-import of an existing scene, the Scene Analyzer compares old metadata vs new extracted metadata and proposes *deletions* and *modifications* to the bible, not just additions. The writer reviews the full diff before confirming. |
| Slow analysis (local inference) | Chat responses stream token by token via websocket. Scene import shows step-by-step progress. Writer never faces a blank spinner. |
| Initial data entry burden | Provide a bulk import mode: drop existing scene files → batch Scene Analyzer run to bootstrap the bible. |

---

## 11. Open Questions

- [ ] What are the writer's Mac specs? (chip + RAM → model ceiling). Known: more RAM than 16GB, but older chip generation. Need exact specs to pick model.
- [x] ~~Does he already have scene files in a specific format?~~ → Plain text.
- [ ] How many scenes / how much content approximately? (vector DB sizing)
- [x] ~~Does he need multi-user support?~~ → No, single writer.
- [ ] Embedding model choice: nomic-embed-text vs mxbai-embed-large — benchmark needed on his hardware
- [x] ~~Should the scene editor be the primary writing tool?~~ → No. It's a check & query tool. He writes elsewhere, imports finished scenes, then asks the system coherence questions in natural language.

---

## 12. Implementation Phases

**Phase 0 — Proof of concept**
Chat Agent with tools (get_character, get_timeline, search_scenes) + hand-crafted SQLite bible + ChromaDB. CLI chat loop. Validate that the target model can answer coherence questions using tools.

**Phase 1 — Scene import pipeline**
Scene Analyzer agent. Import plain text → extract metadata → check coherence against existing bible → writer reviews and confirms → commit to bible + RAG. Still CLI.

**Phase 2 — Web interface**
FastAPI + vanilla frontend. Bible Manager (CRUD) + scene import + chat. Docker packaging.

**Phase 3 — Polish**
Timeline visualization. Bulk scene import. Streaming UX. Prompt tuning based on real usage.