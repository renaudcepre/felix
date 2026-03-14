from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite
    import chromadb


@dataclass
class FelixDeps:
    db: aiosqlite.Connection
    chroma_collection: chromadb.Collection
