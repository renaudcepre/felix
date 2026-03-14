"""Run the Felix evaluation pipeline."""

from __future__ import annotations

from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.providers.mistral import MistralProvider
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import LLMJudge

from evals.evaluators import ContainsExpectedFacts, RefusesToFabricate
from evals.task import felix_task
from felix.config import settings

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
    report = dataset.evaluate_sync(felix_task)
    report.print(include_input=True, include_output=True)


if __name__ == "__main__":
    main()
