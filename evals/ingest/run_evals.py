"""Run the Felix scene analysis evaluation pipeline.

Usage:
    uv run python -m evals.ingest.run_evals --local
    uv run python -m evals.ingest.run_evals --local --model qwen2.5-7b-instruct-1m
"""

from __future__ import annotations

import argparse
import os

from pydantic_evals import Case, Dataset

from evals.ingest.evaluators import (
    CharacterRoleAccuracy,
    EraAccuracy,
    ExtractsExpectedCharacters,
    LocationAccuracy,
    NoCharacterPresent,
)
from evals.ingest.task import analyze_scene_task
from felix.config import settings

LMSTUDIO_URL = "http://localhost:1234/v1"
LMSTUDIO_DEFAULT_MODEL = "qwen2.5-7b-instruct-1m"


dataset = Dataset[str, object](
    cases=[
        # --- Scene 1: Jakes Milton in the mine ---
        Case(
            name="scene1_character_roles",
            inputs="001-la-poussiere.txt",
            expected_output="Jakes Milton:participant,Mite:participant,Elias:mentioned",
            metadata={"category": "roles", "scene": "001"},
            evaluators=[CharacterRoleAccuracy()],
        ),
        Case(
            name="scene1_all_characters",
            inputs="001-la-poussiere.txt",
            expected_output="Jakes Milton,Mite,Elias",
            metadata={"category": "extraction", "scene": "001"},
            evaluators=[ExtractsExpectedCharacters()],
        ),
        Case(
            name="scene1_era",
            inputs="001-la-poussiere.txt",
            expected_output="2050s",
            metadata={"category": "era", "scene": "001"},
            evaluators=[EraAccuracy()],
        ),
        Case(
            name="scene1_location",
            inputs="001-la-poussiere.txt",
            expected_output="Fosse 72",
            metadata={"category": "location", "scene": "001"},
            evaluators=[LocationAccuracy()],
        ),
        # --- Scene 2: Andrew Milton in orbit ---
        Case(
            name="scene2_character_roles",
            inputs="002-l-orbite.txt",
            expected_output="Andrew Milton:participant,M.I.T.E.:participant,Jakes:mentioned",
            metadata={"category": "roles", "scene": "002"},
            evaluators=[CharacterRoleAccuracy()],
        ),
        Case(
            name="scene2_all_characters",
            inputs="002-l-orbite.txt",
            expected_output="Andrew Milton,M.I.T.E.,Jakes",
            metadata={"category": "extraction", "scene": "002"},
            evaluators=[ExtractsExpectedCharacters()],
        ),
        Case(
            name="scene2_era",
            inputs="002-l-orbite.txt",
            expected_output="2140s",
            metadata={"category": "era", "scene": "002"},
            evaluators=[EraAccuracy()],
        ),
        Case(
            name="scene2_location",
            inputs="002-l-orbite.txt",
            expected_output="Aegis-7",
            metadata={"category": "location", "scene": "002"},
            evaluators=[LocationAccuracy()],
        ),
        # --- Negative: Andrew must NOT appear in scene 1 ---
        Case(
            name="scene1_no_andrew",
            inputs="001-la-poussiere.txt",
            expected_output="Andrew Milton",
            metadata={"category": "negative", "scene": "001"},
            evaluators=[NoCharacterPresent()],
        ),
    ],
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Felix ingest evals")
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

    model_name = os.environ.get("FELIX_EVAL_MODEL", settings.felix_model)
    base_url = os.environ.get("FELIX_EVAL_BASE_URL", "Mistral API")
    print(f"Model: {model_name}")
    print(f"Provider: {base_url}\n")

    report = dataset.evaluate_sync(analyze_scene_task)
    report.print(include_input=True, include_output=True)


if __name__ == "__main__":
    main()
