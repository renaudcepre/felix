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

# Remove database and vector store
db-clean:
    rm -f {{ db_path }}
    rm -rf {{ chroma_path }}
    @echo "DB and ChromaDB cleaned."

# Archive database then clean
db-archive:
    mkdir -p {{ archive_dir }}
    @if [ -f {{ db_path }} ]; then \
        ts=$(date +%Y%m%d-%H%M%S); \
        cp {{ db_path }} {{ archive_dir }}/felix-${ts}.db; \
        echo "Archived to {{ archive_dir }}/felix-${ts}.db"; \
    else \
        echo "No DB to archive."; \
    fi
    @if [ -d {{ chroma_path }} ]; then \
        ts=$(date +%Y%m%d-%H%M%S); \
        tar -czf {{ archive_dir }}/chroma-${ts}.tar.gz {{ chroma_path }}; \
        echo "Archived to {{ archive_dir }}/chroma-${ts}.tar.gz"; \
    fi
    rm -f {{ db_path }}
    rm -rf {{ chroma_path }}
    @echo "Cleaned."
