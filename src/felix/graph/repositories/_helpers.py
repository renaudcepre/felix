"""Shared helpers for repository modules."""


def _nullify_empty(v: str | None) -> str | None:
    return v if v and v.strip() else None
