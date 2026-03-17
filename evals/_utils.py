"""Shared utilities for eval suites."""

from __future__ import annotations

import unicodedata


def normalize(text: str) -> str:
    """Lowercase + strip accents (NFKD + remove combining marks)."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))
