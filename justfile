# Felix — task runner
# Usage: just <recipe>
# just dev-up   → API (hot reload) + frontend Nuxt en parallèle
# just api      → API seule
# just web      → frontend seul

chroma_path := "chroma_data"
archive_dir := "data/archives"

# Lance API FastAPI (hot reload) + frontend Nuxt en parallèle
dev-up:
    #!/usr/bin/env bash
    uv run felix-api &
    API_PID=$!
    cd web && pnpm dev
    kill $API_PID 2>/dev/null || true

# Lance uniquement l'API FastAPI avec hot reload (port 8000)
api:
    uv run felix-api

# Lance uniquement le frontend Nuxt avec hot reload (port 3007)
web:
    cd web && pnpm dev

# Lance les tests via protest
test *args:
    uv run protest run tests.session:session {{ args }}

# Evals du bot B (atelier) — session séparée ; wipe le graphe
evals-atelier *args:
    uv run protest eval evals.atelier.session:session {{ args }}

# Evals du prototype generic-core (schemaless) — session séparée ; wipe le graphe
evals-generic *args:
    uv run protest eval evals.generic.session:session {{ args }}

# E2E de la route atelier SSE (in-process) — joue « Le Nadir », asserte les
# invariants événementiels. ≈40 appels LLM ; wipe le graphe, ne pas lancer avec l'API.
e2e-atelier *args:
    uv run python evals/atelier/e2e.py {{ args }}

# E2E « naturel » du chef d'orchestre (maître) — conversation mêlée (salutations,
# contenu, questions) ; mesure 0 hallucination + recall + 0 placeholder. ≈25 appels
# LLM ; wipe le graphe, ne pas lancer avec l'API.
e2e-conductor *args:
    uv run python evals/atelier/conductor_e2e.py {{ args }}

# E2E human-in-the-loop (#61) — DELETE/PATCH d'entités via l'API pendant une
# conversation ; asserte 0 résurrection + rename respecté. ≈10 appels LLM ;
# wipe le graphe, ne pas lancer avec l'API.
# (-m : le script importe play_turn depuis evals.atelier.e2e)
e2e-edits *args:
    uv run python -m evals.atelier.user_edits_e2e {{ args }}

# Historique des evals
evals-history *args:
    uv run protest history --evals {{ args }}

# Remove database and vector store
db-clean:
    rm -rf {{ chroma_path }}
    docker compose exec neo4j cypher-shell -u neo4j -p felixpassword "MATCH (n) DETACH DELETE n"
    @echo "ChromaDB and Neo4j cleaned."

# Archive database then clean
db-archive:
    mkdir -p {{ archive_dir }}
    @if [ -d {{ chroma_path }} ]; then \
        ts=$(date +%Y%m%d-%H%M%S); \
        tar -czf {{ archive_dir }}/chroma-${ts}.tar.gz {{ chroma_path }}; \
        echo "Archived to {{ archive_dir }}/chroma-${ts}.tar.gz"; \
    fi
    rm -rf {{ chroma_path }}
    docker compose exec neo4j cypher-shell -u neo4j -p felixpassword "MATCH (n) DETACH DELETE n"
    @echo "Cleaned."

# View a .jsonl history file
view-history *args:
    python3 tools/view_history.py {{ args }}
