from __future__ import annotations

import asyncio
from pathlib import Path

from felix.config import settings
from felix.db.schema import init_db
from felix.db.seed import seed_db
from felix.vectorstore.seed import seed_scenes
from felix.vectorstore.store import get_collection


async def run_seed() -> None:
    # Ensure data directory exists
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"Initializing SQLite database at {settings.db_path}...")
    db = await init_db(str(settings.db_path))

    print("Seeding characters, locations, events, relations...")
    await seed_db(db)
    await db.close()

    print("Seeding ChromaDB scenes...")
    collection = get_collection()
    seed_scenes(collection)

    print(f"Done. {collection.count()} scene(s) in ChromaDB.")
    print("Database and vector store ready.")


def main() -> None:
    asyncio.run(run_seed())


if __name__ == "__main__":
    main()
