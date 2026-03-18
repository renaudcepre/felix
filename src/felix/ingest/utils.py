"""Shared utilities for the ingest pipeline."""
from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Fast heuristic token count (word-based, ±15% for FR/EN mixed text)."""
    return int(len(text.split()) * 1.35)
