from __future__ import annotations

from felix.config import settings


def setup_logfire() -> None:
    """Configure Logfire + instrumentation pydantic-ai.

    Nécessite FLX_LOGFIRE_TOKEN (ou LOGFIRE_TOKEN via alias) dans l'env.
    Sans token, la fonction est un no-op.
    """
    if not settings.logfire_token:
        return
    import logfire  # optional dependency — import only when token is present
    logfire.configure(token=settings.logfire_token)
    logfire.instrument_pydantic_ai()
