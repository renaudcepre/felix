# Felix — task runner
# Usage: just <recipe>
# just dev-up   → API (hot reload) + frontend Nuxt en parallèle
# just api      → API seule
# just web      → frontend seul

db_path := "data/felix.db"
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

# Lance uniquement le frontend Nuxt avec hot reload (port 3000)
web:
    cd web && pnpm dev

# Lance les tests pytest
test *args:
    uv run pytest {{ args }}

# Evals (auto-detect LM Studio ou Together AI) — options: --suite, --case, --list, --together, --local
evals *args:
    uv run python -m evals.run_evals {{ args }}

# Remove database and vector store
db-clean:
    rm -f {{ db_path }}
    rm -rf {{ chroma_path }}
    docker compose exec neo4j cypher-shell -u neo4j -p felixpassword "MATCH (n) DETACH DELETE n"
    @echo "DB, ChromaDB and Neo4j cleaned."

# Export graph DB vers exports/<timestamp>.json
export:
    uv run felix-export

# Archive database then clean
db-archive:
    mkdir -p {{ archive_dir }}
    @if [ -d {{ chroma_path }} ]; then \
        ts=$(date +%Y%m%d-%H%M%S); \
        tar -czf {{ archive_dir }}/chroma-${ts}.tar.gz {{ chroma_path }}; \
        echo "Archived to {{ archive_dir }}/chroma-${ts}.tar.gz"; \
    fi
    rm -f {{ db_path }}
    rm -rf {{ chroma_path }}
    docker compose exec neo4j cypher-shell -u neo4j -p felixpassword "MATCH (n) DETACH DELETE n"
    @echo "Cleaned."
