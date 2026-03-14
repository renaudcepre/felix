from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    import aiosqlite

from felix.db.schema import init_db
from felix.db.seed import seed_db


@pytest.fixture
async def seeded_db() -> AsyncGenerator[aiosqlite.Connection]:
    db = await init_db(":memory:")
    await seed_db(db)
    yield db
    await db.close()
