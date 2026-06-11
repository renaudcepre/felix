"""Tests unitaires pour is_transient_error (evals._utils).

Vérifie la classification des exceptions en transients récupérables
(5xx, 429, timeout) vs erreurs franches (400, ValueError, AssertionError).

Anti-leakage : noms de ce module (Reldar, Sontave, Morvex) n'entrent
pas dans les prompts des agents (src/felix/).
"""
from __future__ import annotations

from protest import ProTestSuite

from evals._utils import is_transient_error

backoff_suite = ProTestSuite("Backoff")

# ─────────────────────── Cas TRANSIENTS (True attendu) ────────────────────────


@backoff_suite.test()
def test_500_is_transient() -> None:
    """HTTP 500 Internal Server Error → transient."""
    exc = Exception("HTTP 500 Internal Server Error from Mistral")
    assert is_transient_error(exc)


@backoff_suite.test()
def test_504_is_transient() -> None:
    """HTTP 504 Gateway Timeout → transient."""
    exc = Exception("status code 504 Gateway Timeout")
    assert is_transient_error(exc)


@backoff_suite.test()
def test_429_is_transient() -> None:
    """HTTP 429 Too Many Requests → transient."""
    exc = Exception("Error 429 Too Many Requests")
    assert is_transient_error(exc)


@backoff_suite.test()
def test_rate_limit_is_transient() -> None:
    """Message 'rate limit' → transient (quota API)."""
    exc = Exception("rate limit exceeded, retry later")
    assert is_transient_error(exc)


@backoff_suite.test()
def test_timeout_string_is_transient() -> None:
    """Message 'timeout' → transient (délai réseau)."""
    exc = Exception("connection timeout after 90s")
    assert is_transient_error(exc)


@backoff_suite.test()
def test_timeout_exception_is_transient() -> None:
    """TimeoutError Python natif → transient."""
    exc = TimeoutError("timed out waiting for response")
    assert is_transient_error(exc)


# ─────────────────────── Cas FRANCS (False attendu) ───────────────────────────


@backoff_suite.test()
def test_400_is_not_transient() -> None:
    """HTTP 400 Bad Request → erreur de requête, NE PAS retenter."""
    exc = Exception("HTTP 400 Bad Request: invalid payload")
    assert not is_transient_error(exc)


@backoff_suite.test()
def test_valueerror_is_not_transient() -> None:
    """ValueError générique → erreur applicative, NE PAS retenter."""
    exc = ValueError("invalid data received from model")
    assert not is_transient_error(exc)


@backoff_suite.test()
def test_assertion_error_is_not_transient() -> None:
    """AssertionError → verdict d'eval ou erreur de logique, NE PAS retenter."""
    exc = AssertionError("expected True but got False")
    assert not is_transient_error(exc)
