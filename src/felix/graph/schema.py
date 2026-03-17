from __future__ import annotations

import kuzu

_NODE_TABLES = [
    "CREATE NODE TABLE IF NOT EXISTS Character(id STRING, name STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Scene(id STRING, title STRING, date STRING, era STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Location(id STRING, name STRING, PRIMARY KEY(id))",
]

_REL_TABLES = [
    "CREATE REL TABLE IF NOT EXISTS PRESENT_IN(FROM Character TO Scene, role STRING)",
    "CREATE REL TABLE IF NOT EXISTS AT_LOCATION(FROM Scene TO Location)",
]


def init_graph(path: str | None = None) -> kuzu.Database:
    """Initialize Kuzu graph DB. Pass path for persistent storage, None for in-memory."""
    db = kuzu.Database(path) if path else kuzu.Database()
    conn = kuzu.Connection(db)
    for stmt in _NODE_TABLES + _REL_TABLES:
        conn.execute(stmt)
    return db
