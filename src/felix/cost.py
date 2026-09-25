"""Comptabilité UNIQUE des coûts LLM — un `CostLedger` par opération (tour de
chat, import de document), alimenté par TOUS les appels (gate, maître,
extracteurs, juge de cohérence), jamais une copie par appelant (cf. CLAUDE.md
« des systèmes, pas du cas par cas » — trois compteurs de coût réécrits à la
main auraient exactement le même défaut que `cabinets_left`/`amp_is_out`).

Prix en USD par MILLION de tokens, table par défaut + surcharge JSON
(`FLX_PRICING_JSON`, cf. `felix.config.Settings.pricing_json`). Un modèle
absent de la table (défauts + surcharge) a un prix INCONNU : jamais remplacé
par 0€ (un faux 0 mentirait sur le coût réel), le champ `cost_usd` reste
`None` et l'UI affiche « prix inconnu ».
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from felix.config import settings

if TYPE_CHECKING:
    from pydantic_ai import Agent
    from pydantic_ai.usage import RunUsage, UsageBase

logger = logging.getLogger(__name__)


def agent_model_name(agent: Agent[Any, Any]) -> str:
    """Nom du modèle RÉELLEMENT utilisé par un `Agent` pydantic-ai — l'attribution
    par appel dont dépend tout ce module (gate/maître/checker peuvent différer,
    cf. build_gate_model/build_checker_model/build_chat_model).

    `Agent.model` est typé `Model | str | None` côté pydantic-ai (un agent PEUT
    être construit avec un simple nom de modèle) ; dans ce projet, TOUS les
    agents sont construits via `felix.llm.build_model`, qui rend toujours un
    `Model` concret — jamais une string. L'assert documente cet invariant (et
    lève fort s'il est un jour violé, plutôt qu'un coût silencieusement perdu)."""
    model = agent.model
    if model is None or isinstance(model, str):
        msg = f"agent construit sans Model concret (model={model!r}) — coût non attribuable"
        raise TypeError(msg)
    return model.model_name


class PriceEntry(BaseModel):
    """Prix d'UN modèle, en USD par million de tokens (entrée / sortie)."""

    input_per_million: float
    output_per_million: float


# Défauts (2026-09-24). devstral-small-2512, mistral-small-*, mistral-large-latest
# et mistral-medium-latest viennent de la page de pricing officielle Mistral.
# devstral-2512 en est ABSENT (Mistral ne le liste plus) — prix repris
# d'agrégateurs tiers (OpenRouter, pricepertoken, relevé le 2026-09-24) : à
# vérifier si Mistral republie un prix officiel.
DEFAULT_PRICING: dict[str, PriceEntry] = {
    "devstral-2512": PriceEntry(input_per_million=0.40, output_per_million=2.00),
    "devstral-small-2512": PriceEntry(input_per_million=0.10, output_per_million=0.30),
    "mistral-small-latest": PriceEntry(input_per_million=0.15, output_per_million=0.60),
    "mistral-small-2506": PriceEntry(input_per_million=0.15, output_per_million=0.60),
    "mistral-large-latest": PriceEntry(input_per_million=0.50, output_per_million=1.50),
    "mistral-medium-latest": PriceEntry(input_per_million=1.50, output_per_million=7.50),
}


def parse_pricing_overrides(raw: str) -> dict[str, PriceEntry]:
    """Parse la surcharge JSON `{"modele": {"input": x, "output": y}, ...}`.

    Défensif : une chaîne vide, un JSON malformé, une entrée incomplète sont
    IGNORÉS (journalisés) plutôt que de faire planter le démarrage — les
    défauts restent actifs pour les modèles non couverts par la surcharge."""
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("FLX_PRICING_JSON invalide (JSON malformé) — ignoré : %r", raw)
        return {}
    if not isinstance(data, dict):
        logger.warning("FLX_PRICING_JSON doit être un objet JSON — ignoré")
        return {}
    out: dict[str, PriceEntry] = {}
    for name, prices in data.items():
        try:
            out[name] = PriceEntry(
                input_per_million=float(prices["input"]),
                output_per_million=float(prices["output"]),
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("entrée de prix invalide pour %r dans FLX_PRICING_JSON — ignorée", name)
    return out


def build_pricing_table(overrides_json: str | None = None) -> dict[str, PriceEntry]:
    """Table de prix effective : défauts + surcharge.

    `overrides_json` explicite (tests) sinon `settings.pricing_json` (prod, lu
    à chaque appel — pas de cache, la table reste bon marché à reconstruire).
    Une entrée de la surcharge remplace ENTIÈREMENT le défaut du même nom."""
    table = dict(DEFAULT_PRICING)
    raw = overrides_json if overrides_json is not None else settings.pricing_json
    table.update(parse_pricing_overrides(raw))
    return table


def price_for_model(model_name: str, *, overrides_json: str | None = None) -> PriceEntry | None:
    """Prix du modèle, ou `None` si absent de la table (prix inconnu)."""
    return build_pricing_table(overrides_json).get(model_name)


class ModelCost(BaseModel):
    """Coût attribué à UN modèle dans une opération (tour de chat, import de
    document, ou passes de vérification de cohérence)."""

    model: str
    request_tokens: int
    response_tokens: int
    total_tokens: int
    cost_usd: float | None


class CostSummary(BaseModel):
    """Total agrégé d'une opération, éclaté par modèle.

    `cost_usd` (total) est `None` si AU MOINS un modèle utilisé a un prix
    inconnu — jamais un total tronqué qui sous-estimerait silencieusement la
    dépense réelle (même règle « jamais un faux 0 » que par modèle)."""

    request_tokens: int
    response_tokens: int
    total_tokens: int
    cost_usd: float | None
    by_model: list[ModelCost]


@dataclass
class CostLedger:
    """Le système de comptabilité unique d'une opération. `add`/`add_usage` sont
    appelés par CHAQUE passe LLM (gate, maître, extracteurs, juge de
    cohérence) — jamais une liste ad hoc recréée par l'appelant."""

    _entries: list[tuple[str, int, int]] = field(default_factory=list)

    def add(self, model_name: str, request_tokens: int, response_tokens: int) -> None:
        self._entries.append((model_name, request_tokens or 0, response_tokens or 0))

    def add_usage(self, model_name: str, usage: RunUsage | UsageBase) -> None:
        """Raccourci depuis un `RunUsage` pydantic-ai (`run.usage()`)."""
        self.add(model_name, usage.input_tokens, usage.output_tokens)

    def merge(self, other: CostLedger) -> None:
        """Fusionne les entrées d'un autre ledger (ex. le ledger d'un bloc
        d'ingestion dans le ledger du document entier) — même esprit que
        `GenericDeps.touched_ids |= chunk_deps.touched_ids`."""
        self._entries.extend(other._entries)  # même classe, accès direct légitime

    def summary(self, *, pricing_overrides: str | None = None) -> CostSummary:
        """Agrège les entrées par modèle et calcule le prix — un seul calcul
        par modèle (pas par appel LLM individuel)."""
        table = build_pricing_table(pricing_overrides)
        by_model: dict[str, ModelCost] = {}
        for model_name, req_tok, resp_tok in self._entries:
            existing = by_model.get(model_name)
            if existing is None:
                by_model[model_name] = ModelCost(
                    model=model_name, request_tokens=req_tok, response_tokens=resp_tok,
                    total_tokens=req_tok + resp_tok, cost_usd=None,
                )
            else:
                existing.request_tokens += req_tok
                existing.response_tokens += resp_tok
                existing.total_tokens += req_tok + resp_tok

        total_request = total_response = total_tokens = 0
        total_cost: float | None = 0.0
        for mc in by_model.values():
            total_request += mc.request_tokens
            total_response += mc.response_tokens
            total_tokens += mc.total_tokens
            price = table.get(mc.model)
            if price is None:
                mc.cost_usd = None
                total_cost = None
            else:
                mc.cost_usd = (
                    mc.request_tokens * price.input_per_million
                    + mc.response_tokens * price.output_per_million
                ) / 1_000_000
                if total_cost is not None:
                    total_cost += mc.cost_usd

        return CostSummary(
            request_tokens=total_request, response_tokens=total_response,
            total_tokens=total_tokens, cost_usd=total_cost,
            by_model=list(by_model.values()),
        )
