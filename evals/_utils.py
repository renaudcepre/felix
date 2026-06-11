"""Utilitaires partagés entre les suites d'evals."""
from __future__ import annotations

import asyncio
import unicodedata


def normalize(text: str) -> str:
    """Lowercase + strip accents (NFKD + suppression des marques combinantes)."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def is_transient_error(exc: Exception) -> bool:
    """Retourne True si l'exception est un transient récupérable.

    Transients : 5xx serveur (500/502/503/504), 429 rate-limit, timeout réseau.
    NON-transients : 400 (erreur de requête), ValueError, AssertionError, etc.
    Un 400 n'est jamais retenté : c'est une erreur de contenu, pas d'infra."""
    # Timeouts Python natifs (inclut asyncio.TimeoutError en Python 3.11+)
    if isinstance(exc, TimeoutError):
        return True
    # Timeout par nom de classe (httpx.TimeoutException et variantes)
    if "timeout" in type(exc).__qualname__.lower():
        return True
    # Codes HTTP dans le message (pydantic-ai encapsule le code dans la str)
    msg = str(exc).lower()
    return any(
        pattern in msg
        for pattern in ("429", "rate", "timeout", "500", "502", "503", "504")
    )


async def with_backoff(make_coro, attempts: int = 3) -> object:
    """Backoff exponentiel sur les transients Mistral (429, 5xx, timeout).

    pydantic-ai ne retente pas ces erreurs d'infrastructure. On rejoue le même
    appel (même lambda, même historique) avec un délai croissant : 3 s, 6 s, 12 s.
    Ne retente JAMAIS un verdict d'eval (AssertionError, ValueError) ni un 400."""
    delay = 3.0
    last: Exception | None = None
    for _ in range(attempts):
        try:
            return await make_coro()
        except Exception as exc:
            if not is_transient_error(exc):
                raise
            last = exc
            await asyncio.sleep(delay)
            delay *= 2
    raise last  # type: ignore[misc]
