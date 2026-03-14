"""Run the Felix evaluation pipeline.

Usage:
    uv run python -m evals.run_evals                    # Mistral API (default)
    uv run python -m evals.run_evals --local             # LMStudio default (meta-llama-3.1-8b-instruct)
    uv run python -m evals.run_evals --local --model qwen2.5-7b-instruct-1m
"""

from __future__ import annotations

import argparse
import os

from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.providers.mistral import MistralProvider
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import LLMJudge

from evals.evaluators import ContainsExpectedFacts, RefusesToFabricate
from evals.task import felix_task
from felix.config import settings

LMSTUDIO_URL = "http://localhost:1234/v1"
LMSTUDIO_DEFAULT_MODEL = "meta-llama-3.1-8b-instruct"

_judge_model = MistralModel(
    "mistral-small-latest",
    provider=MistralProvider(api_key=settings.mistral_api_key),
)

dataset = Dataset[str, str](
    cases=[
        # --- 1. Lookup simple ---
        Case(
            name="lookup_character",
            inputs="Qui est Marie Dupont ?",
            expected_output="Marie, Resistance, 1940s, coursiere",
            metadata={"category": "lookup"},
        ),
        Case(
            name="lookup_location",
            inputs="Decris la planque de Lyon.",
            expected_output="Merciere, librairie, Resistance",
            metadata={"category": "lookup"},
        ),
        # --- 2. Coherence temporelle ---
        Case(
            name="coherence_marie_sarah",
            inputs="Est-ce coherent si Marie rencontre Sarah en mars 1942 ?",
            expected_output="Sarah, mars 1942, Lyon",
            metadata={"category": "coherence"},
        ),
        Case(
            name="coherence_pierre_november",
            inputs="Ou etait Pierre en novembre 1942 ?",
            expected_output="Pierre, arrest, novembre 1942",
            metadata={"category": "coherence"},
        ),
        # --- 3. Recherche semantique ---
        Case(
            name="semantic_identity",
            inputs="Trouve les scenes ou quelqu'un decouvre une identite secrete.",
            expected_output="042, identite, Vichy",
            metadata={"category": "semantic"},
        ),
        Case(
            name="semantic_archives",
            inputs="Que se passe-t-il dans les archives ?",
            expected_output="088, Julien, archives, Laforge",
            metadata={"category": "semantic"},
        ),
        # --- 4. Cross-era ---
        Case(
            name="cross_era_benoit_julien",
            inputs=(
                "Quel est le lien entre Benoit dans les annees 40 "
                "et les documents que Julien trouve ?"
            ),
            expected_output="agent double, Laforge, carbone, Resistance",
            metadata={"category": "cross_era"},
        ),
        # --- 5. Tests negatifs ---
        Case(
            name="negative_car_color",
            inputs="De quelle couleur est la voiture de Marie ?",
            expected_output="",
            metadata={"category": "negative"},
            evaluators=[RefusesToFabricate()],
        ),
        Case(
            name="negative_julien_brother",
            inputs="Qui est le frere de Julien ?",
            expected_output="",
            metadata={"category": "negative"},
            evaluators=[RefusesToFabricate()],
        ),
    ],
    evaluators=[
        ContainsExpectedFacts(),
        LLMJudge(
            rubric=(
                "The response is factually grounded: it only states information "
                "that could have been retrieved from a screenplay bible database "
                "(character profiles, timeline events, scene text). "
                "It does not invent or hallucinate any facts."
            ),
            model=_judge_model,
            include_input=True,
        ),
    ],
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Felix evals")
    parser.add_argument(
        "--local", action="store_true", help="Use LMStudio local model"
    )
    parser.add_argument(
        "--model", type=str, default=None, help="Model name override"
    )
    parser.add_argument(
        "--base-url", type=str, default=None, help="OpenAI-compatible base URL"
    )
    args = parser.parse_args()

    if args.local:
        os.environ["FELIX_EVAL_BASE_URL"] = args.base_url or LMSTUDIO_URL
        os.environ["FELIX_EVAL_MODEL"] = args.model or LMSTUDIO_DEFAULT_MODEL
    elif args.model:
        os.environ["FELIX_EVAL_MODEL"] = args.model
    elif args.base_url:
        os.environ["FELIX_EVAL_BASE_URL"] = args.base_url

    model_name = os.environ.get("FELIX_EVAL_MODEL", settings.mistral_model)
    base_url = os.environ.get("FELIX_EVAL_BASE_URL", "Mistral API")
    print(f"Model: {model_name}")
    print(f"Provider: {base_url}\n")

    report = dataset.evaluate_sync(felix_task)
    report.print(include_input=True, include_output=True)


if __name__ == "__main__":
    main()
