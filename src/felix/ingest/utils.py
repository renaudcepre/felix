"""Shared utilities for the ingest pipeline."""
from __future__ import annotations

import unicodedata


def normalize(name: str) -> str:
    """Lowercase + strip accents for fuzzy matching."""
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def estimate_tokens(text: str) -> int:
    """Fast heuristic token count (word-based, ±15% for FR/EN mixed text)."""
    return int(len(text.split()) * 1.35)
