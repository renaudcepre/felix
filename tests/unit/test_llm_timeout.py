"""Le timeout HTTP doit ATTEINDRE les requêtes Mistral (gel de 900 s vécu).

Constat du 2026-06-11 (run d'eval gelé 15 min) : le SDK mistralai construit
chaque requête avec `timeout=timeout_ms/1000 if timeout_ms else None` — et en
httpx, un timeout PAR REQUÊTE à None DÉSACTIVE le timeout au lieu d'hériter de
celui du client. Le `httpx.Timeout(90.0)` posé sur l'AsyncClient était donc
décoratif : le gateway Mistral (Kong) peut tenir une connexion 900 s avant de
rendre un 504, et on attend tout du long.

La loi vérifiée ici : le client SDK Mistral construit par build_model porte un
`timeout_ms` explicite — c'est LE canal que le SDK honore vraiment.
"""
from __future__ import annotations

from protest import ProTestSuite

from felix.llm import build_model

llm_timeout_suite = ProTestSuite("LlmTimeout")


@llm_timeout_suite.test()
def test_mistral_sdk_carries_explicit_timeout() -> None:
    """Le SDK mistralai doit porter un timeout_ms explicite (sinon : requêtes
    sans timeout, gels silencieux de 15 min sur gateway muet)."""
    model = build_model("mistral-small-2506")
    timeout_ms = model.client.sdk_configuration.timeout_ms
    assert timeout_ms is not None, (
        "timeout_ms absent du client SDK Mistral : chaque requête part SANS "
        "timeout (le None par requête écrase le timeout du client httpx)"
    )
    assert 30_000 <= timeout_ms <= 300_000, f"timeout_ms aberrant : {timeout_ms}"
