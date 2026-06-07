"""Dépendances du bot B (atelier) — ré-export du noyau générique.

L'inversion de dépendance a fait de GenericDeps la classe racine ; AtelierDeps
en est un alias conservé pour la compatibilité des imports (route SSE, evals).
"""
from __future__ import annotations

from felix.core.deps import GenericDeps as AtelierDeps

__all__ = ["AtelierDeps"]
