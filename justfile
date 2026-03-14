# Felix — task runner

db_path := "data/felix.db"
chroma_path := "chroma_data"
archive_dir := "data/archives"

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
