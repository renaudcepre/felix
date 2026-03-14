import aiosqlite

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS characters (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    aliases     TEXT,
    era         TEXT NOT NULL,
    age         TEXT,
    physical    TEXT,
    background  TEXT,
    arc         TEXT,
    traits      TEXT,
    status      TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS locations (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    era         TEXT,
    description TEXT,
    address     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS timeline_events (
    id          TEXT PRIMARY KEY,
    date        TEXT NOT NULL,
    era         TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    location_id TEXT REFERENCES locations(id),
    scene_id    TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS character_events (
    character_id TEXT NOT NULL REFERENCES characters(id),
    event_id     TEXT NOT NULL REFERENCES timeline_events(id),
    role         TEXT,
    PRIMARY KEY (character_id, event_id)
);

CREATE TABLE IF NOT EXISTS character_relations (
    character_id_a TEXT NOT NULL REFERENCES characters(id),
    character_id_b TEXT NOT NULL REFERENCES characters(id),
    relation_type  TEXT NOT NULL,
    description    TEXT,
    era            TEXT,
    PRIMARY KEY (character_id_a, character_id_b, relation_type)
);
"""


async def init_db(db_path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.executescript(SCHEMA_SQL)
    await db.commit()
    return db
