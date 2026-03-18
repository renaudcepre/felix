from __future__ import annotations

import logging

from felix.config import settings


def setup_logging() -> None:
    """Configure stdlib logging with level from settings.
    
    Idempotent — no-op if handlers already configured.
    """
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def setup_logfire() -> None:
    """Configure Logfire + instrumentation pydantic-ai.

    Nécessite FLX_LOGFIRE_TOKEN (ou LOGFIRE_TOKEN via alias) dans l'env.
    Sans token, la fonction est un no-op.
    """
    setup_logging()  # always configure stdlib first
    if not settings.logfire_token:
        return
    import logfire  # optional dependency — import only when token is present
    logfire.configure(token=settings.logfire_token)
    logfire.instrument_pydantic_ai()
