from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from felix.atelier.models import ToolCard


@dataclass
class AtelierDeps:
    driver: AsyncDriver
    # Cartes structurées poussées par les tools pendant le run,
    # drainées par la route SSE (et lues telles quelles par les evals).
    ui_events: list[ToolCard] = field(default_factory=list)
