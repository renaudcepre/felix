# Felix

Felix turns documents and conversation into a knowledge graph. You import a
document or describe something in chat, and Felix extracts entities and
relations, checks them for consistency against the source, and answers
questions about what is in the graph. It is domain-agnostic: a mode picks the
vocabulary (what counts as an entity, what relations are allowed), but the
pipeline underneath is the same for a screenplay, a construction log, or a
maintenance manual. The `emergent` mode has no fixed vocabulary at all: it
learns one from the documents you feed it, with a human validating every
change before it becomes part of the schema.

---

## Modes

| Mode | Vocabulary | Use case |
|---|---|---|
| `scenario` | Characters, scenes, locations, timeline events | Multi-era screenplay continuity |
| `chantier` | Tools, materials, work items, participants | Construction site progress log |
| `maintenance` | Machine, part, control, parameter, mode, instruction, document | Technical documentation, fixed schema |
| `emergent` | Starts empty, learns types and relations from documents | Unknown domain, default mode |
| `none` | No profile at all | Bare core, nothing assumed |

Modes are defined in `src/felix/atelier/agent.py` (`ATELIER_CHOICES`) and
`src/felix/core/profile.py`. The mode selector in `/chat` calls
`GET /api/atelier/profiles`.

---

## Architecture

- **Gate**: one short, stateless call per turn. No tools, no history. Decides
  whether a message asserts a fact worth extracting.
- **Master**: leads the conversation, read-only tools only (`find_entity`,
  `list_entities`). It cannot write to the graph, so a greeting or a question
  never creates anything.
- **Extractors**: three passes run after the gate opens: entity extraction,
  relation binding, and (if the mode tracks events) chronicling. Chat and
  document import share the same extraction pipeline
  (`src/felix/atelier/pipeline.py`).
- **Checker + source verifier**: a consistency check scans the graph for
  contradictions; a second, source-grounded check reads the original document
  pages to tell a real inconsistency in the document from a bad reading by
  Felix.
- **Graph**: Neo4j, every node and relation scoped to a project (`project`
  property on every node, enforced by an AST guard and a runtime probe). One
  Neo4j instance holds every project.
- **Emergent profile loop** (`emergent` mode only): a deterministic detector
  scans recurring verbs and near-duplicate types and proposes schema changes;
  a human accepts or rejects each one in the Propositions panel; an accepted
  change migrates past data (`src/felix/core/schema_changes.py`), so validated
  vocabulary applies retroactively, not just going forward.

---

## Quick start

1. Start Neo4j:

   ```bash
   docker compose up -d
   ```

   Neo4j Browser is at `http://localhost:7474`. Bolt is at
   `bolt://localhost:7687`.

2. Create a `.env` file at the project root. All settings use the `FLX_`
   prefix (see `src/felix/config.py` for the full list). At minimum, pick one
   LLM provider:

   | Variable | What it does |
   |---|---|
   | `FLX_LLM_API_KEY` | Mistral API key |
   | `TOGETHER_API_KEY` | Together AI key (alternative provider) |
   | `FLX_LLM_MODEL` | Model name |
   | `FLX_LLM_BASE_URL` | OpenAI-compatible base URL (Together AI, LM Studio) |
   | `FLX_NEO4J_URI` / `FLX_NEO4J_USER` / `FLX_NEO4J_PASSWORD` | Neo4j connection, matches `docker-compose.yml` defaults |

   `.env.example` has a working template for Mistral, Together AI, and a
   local LM Studio server.

3. Install and run:

   ```bash
   uv sync
   just dev-up
   ```

   This starts the API (port 8000, hot reload) and the Nuxt frontend (port
   3007) together.

4. Open `http://localhost:3007/chat`. Pick a project and a mode (`emergent`
   is the default).

5. Import the sample fixture: use the "Importer une fiche" button and select
   `evals/maintenance/fixtures/sx40_fiche.txt`, or run it from the CLI:

   ```bash
   just ingest-doc evals/maintenance/fixtures/sx40_fiche.txt --profile maintenance
   ```

6. Ask a question about the imported document in the chat.

7. Open the Propositions panel (top bar) to see and validate the schema
   changes the emergent detector proposed.

---

## Cost display and pricing

Every chat turn and every document import shows token count and USD cost,
broken down by model. A model with no known price shows as unknown rather
than a false `$0`: the pricing table (`src/felix/cost.py`,
`DEFAULT_PRICING`) never invents a number.

To override or add a price, set `FLX_PRICING_JSON`:

```dotenv
FLX_PRICING_JSON={"my-model": {"input": 0.20, "output": 1.00}}
```

Prices are USD per million tokens. An entry replaces the default for that
model name entirely; it does not merge input/output partially.

---

## Per-role model overrides

Each role can use a different model. Every override falls back to
`FLX_LLM_MODEL` / `FLX_LLM_BASE_URL` if unset.

| Role | Model variable | Base URL variable |
|---|---|---|
| Chat (master) | `FLX_LLM_CHAT_MODEL` | `FLX_LLM_CHAT_BASE_URL` |
| Checker (consistency) | `FLX_LLM_CHECKER_MODEL` | `FLX_LLM_CHECKER_BASE_URL` |
| Gate (routing) | `FLX_LLM_GATE_MODEL` | `FLX_LLM_GATE_BASE_URL` |
| Source verifier | `FLX_LLM_VERIFIER_MODEL` | `FLX_LLM_VERIFIER_BASE_URL` |

The verifier falls back to the checker model if unset, the same way the gate
falls back to chat.

---

## Development

```bash
just test                # unit tests (protest, not pytest)
just web-check            # front: typecheck, lint, build, stops at first failure
just e2e-atelier          # SSE route e2e, plays a scenario story, ~40 LLM calls
just e2e-conductor        # master e2e: greetings, content, questions mixed
just e2e-edits            # human-in-the-loop e2e: delete/patch during a conversation
just ingest-doc <path>    # ingest a document from the CLI, calls the LLM
just schema <cmd>         # emergent schema CLI: profile/proposals/apply, no LLM call
```

`just test` runs against a real Neo4j instance, no mocking. E2E recipes wipe
the graph: do not run them against the API you are using for a demo.

---

## Known limits

- **Text only.** PDF import extracts text; images (photos of buttons,
  indicator lights, diagrams) are dropped. A fiche that is half images loses
  that half.
- **Extraction quality is measured on few documents.** The maintenance and
  emergent pipelines were validated on one synthetic fixture (SX-40, a
  crimping machine sheet written for this repo, no real document). Results on
  other document shapes are unmeasured.
- **Cost per document is an order of magnitude, not a guarantee.** A chat
  turn with extraction runs around 27k tokens (~$0.01-0.02). A document
  import costs much more: measured runs on a short fixture (4 pages, then a
  denser 1.5-page rewrite of the same content) ranged from 270k to 546k
  tokens depending on chunking strategy, dominated by tool round-trips and
  consistency-checker judge calls, not the raw text volume.

No client data and no real document ever went into this repo, its prompts,
or its tests. The only fixture used is the synthetic SX-40 sheet in
`evals/maintenance/fixtures/`.
