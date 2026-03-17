from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import chromadb
    from neo4j import AsyncDriver


@dataclass
class FelixDeps:
    driver: AsyncDriver
    chroma_collection: chromadb.Collection
