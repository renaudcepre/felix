"""Felix eval runner — unified entry point for all eval suites.

Usage:
    uv run python -m evals.run_evals --suite pipeline --openrouter
    uv run python -m evals.run_evals --suite ingest --local
    uv run python -m evals.run_evals --suite chatbot --model mistral-small-latest
    uv run python -m evals.run_evals --suite pipeline --list
    uv run python -m evals.run_evals --suite pipeline --case character_extraction
    uv run python -m evals.run_evals                          # toutes les suites
"""

from __future__ import annotations

import os
from typing import Annotated, Any

import typer
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.providers.mistral import MistralProvider
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import LLMJudge
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from evals._runner import run_with_spinners, setup_model_env
from evals.evaluators import ContainsExpectedFacts, RefusesToFabricate
from evals.ingest.evaluators import (
    CharacterRoleAccuracy,
    EraAccuracy,
    ExtractsExpectedCharacters,
    LocationAccuracy,
    NoCharacterPresent,
)
from evals.ingest.task import analyze_scene_task
from evals.pipeline.evaluators import (
    AllLocationsContainKeyword,
    BackgroundContainsKeywords,
    CharacterAbsent,
    CharacterIdsPresent,
    ExactFragmentCount,
    IssueDescriptionContains,
    IssueTypeAbsent,
    IssueTypePresent,
    LocationContainsKeyword,
    MaxIssueSeverityCount,
    MinFragmentCount,
    MinIssueCount,
    MinRelationsCount,
    RelationWithCharPresent,
)
from evals.pipeline.task import build_pipeline_task
from evals.task import felix_task
from felix.config import settings

console = Console()

# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

_judge_model = MistralModel(
    "mistral-small-latest",
    provider=MistralProvider(api_key=settings.llm_api_key),
)

PIPELINE_DATASET: Dataset[str, Any] = Dataset(
    cases=[
        # --- extraction ---
        Case(
            name="character_extraction",
            inputs="characters",
            expected_output="irina-voss,kofi-adu,chen-wei,yuna-park",
            metadata={"category": "extraction"},
            evaluators=[CharacterIdsPresent()],
        ),
        Case(
            name="location_helios",
            inputs="locations",
            expected_output="helios",
            metadata={"category": "extraction"},
            evaluators=[LocationContainsKeyword()],
        ),
        Case(
            name="negative_unknown_character",
            inputs="characters",
            expected_output="mystery-stranger",
            metadata={"category": "extraction"},
            evaluators=[CharacterAbsent()],
        ),
        # --- appearances ---
        Case(
            name="irina_appearances",
            inputs="irina_fragments",
            expected_output="3",
            metadata={"category": "appearances"},
            evaluators=[MinFragmentCount()],
        ),
        Case(
            name="kofi_appearances",
            inputs="fragments:kofi-adu",
            expected_output="2",
            metadata={"category": "appearances"},
            evaluators=[MinFragmentCount()],
        ),
        # --- profiling ---
        Case(
            name="irina_profile_background",
            inputs="irina_profile",
            expected_output="helios,controle,ingenieur,18,mois",
            metadata={"category": "profiling"},
            evaluators=[BackgroundContainsKeywords(min_match=2)],
        ),
        Case(
            name="kofi_profile_background",
            inputs="profile:kofi-adu",
            expected_output="helios,signal,kofi,adu",
            metadata={"category": "profiling"},
            evaluators=[BackgroundContainsKeywords(min_match=1)],
        ),
        Case(
            name="chen_profile_background",
            inputs="profile:chen-wei",
            expected_output="commandant,helios,chen,wei",
            metadata={"category": "profiling"},
            evaluators=[BackgroundContainsKeywords(min_match=1)],
        ),
        Case(
            name="yuna_profile_background",
            inputs="profile:yuna-park",
            expected_output="helios,recrue,yuna,signal",
            metadata={"category": "profiling"},
            evaluators=[BackgroundContainsKeywords(min_match=1)],
        ),
        # --- consistency ---
        Case(
            name="scene3_consistency_issue",
            inputs="issues:scene-03_intrusion",
            expected_output="1",
            metadata={"category": "consistency"},
            evaluators=[MinIssueCount()],
        ),
        # --- relations ---
        Case(
            name="character_relations",
            inputs="relations",
            expected_output="1",
            metadata={"category": "relations"},
            evaluators=[MinRelationsCount()],
        ),
        # --- character arc / profil cross-scène ---
        Case(
            name="irina_experience_in_profile",
            inputs="profile:irina-voss",
            expected_output="quinze,15,ans,observation",
            metadata={"category": "character_arc", "difficulty": "medium"},
            evaluators=[BackgroundContainsKeywords(min_match=1)],
        ),
        Case(
            name="yuna_appears_exactly_once",
            inputs="fragments:yuna-park",
            expected_output="1",
            metadata={"category": "character_arc", "difficulty": "easy"},
            evaluators=[ExactFragmentCount()],
        ),
        Case(
            name="chen_appears_in_scene2_only",
            inputs="active_fragments:chen-wei",
            expected_output="1",
            metadata={"category": "character_arc", "difficulty": "medium"},
            evaluators=[ExactFragmentCount()],
        ),
        # --- relations inter-personnages ---
        Case(
            name="relation_irina_chen",
            inputs="relations:irina-voss",
            expected_output="chen-wei",
            metadata={"category": "relations", "difficulty": "medium"},
            evaluators=[RelationWithCharPresent()],
        ),
        Case(
            name="relation_kofi_irina",
            inputs="relations:kofi-adu",
            expected_output="irina-voss",
            metadata={"category": "relations", "difficulty": "medium"},
            evaluators=[RelationWithCharPresent()],
        ),
        Case(
            name="relation_kofi_chen_indirect",
            inputs="relations:kofi-adu",
            expected_output="chen-wei",
            metadata={"category": "relations", "difficulty": "hard"},
            evaluators=[RelationWithCharPresent()],
        ),
        # --- cohérence des issues ---
        Case(
            name="yuna_leak_in_issue_description",
            inputs="issues:scene-03_intrusion",
            expected_output="yuna",
            metadata={"category": "issues", "difficulty": "medium"},
            evaluators=[IssueDescriptionContains()],
        ),
        Case(
            name="scene3_has_timeline_issue",
            inputs="issues:scene-03_intrusion",
            expected_output="timeline_inconsistency",
            metadata={"category": "issues", "difficulty": "medium"},
            evaluators=[IssueTypePresent()],
        ),
        Case(
            name="no_error_severity",
            inputs="all_issues",
            expected_output="0",
            metadata={"category": "issues", "difficulty": "hard"},
            evaluators=[MaxIssueSeverityCount(severity="error")],
        ),
        # --- consistance spatiale ---
        Case(
            name="all_locations_at_helios",
            inputs="locations",
            expected_output="helios",
            metadata={"category": "spatial", "difficulty": "hard"},
            evaluators=[AllLocationsContainKeyword()],
        ),
        # --- famille / noms proches ---
        Case(
            name="nakamura_family_extracted",
            inputs="characters",
            expected_output="hana-nakamura,lena-nakamura,kenji-nakamura",
            metadata={"category": "disambiguation", "difficulty": "medium"},
            evaluators=[CharacterIdsPresent()],
        ),
        Case(
            name="nakamura_sisters_related",
            inputs="relations:hana-nakamura",
            expected_output="lena-nakamura",
            metadata={"category": "disambiguation", "difficulty": "medium"},
            evaluators=[RelationWithCharPresent()],
        ),
        Case(
            name="kenji_mentioned_only",
            inputs="active_fragments:kenji-nakamura",
            expected_output="0",
            metadata={"category": "disambiguation", "difficulty": "medium"},
            evaluators=[ExactFragmentCount()],
        ),
        # --- flashback / extraction de date ---
        Case(
            name="flashback_scene_date_correct",
            inputs="scene_date:scene-06_flashback",
            expected_output="2157",
            metadata={"category": "timeline", "difficulty": "medium"},
            evaluators=[BackgroundContainsKeywords(min_match=1)],
        ),
        Case(
            name="flashback_no_false_timeline_issue",
            inputs="issues:scene-06_flashback",
            expected_output="timeline_inconsistency",
            metadata={"category": "timeline", "difficulty": "medium"},
            evaluators=[IssueTypeAbsent()],
        ),
        Case(
            name="irina_kepler9_in_profile",
            inputs="profile:irina-voss",
            expected_output="kepler",
            metadata={"category": "timeline", "difficulty": "medium"},
            evaluators=[BackgroundContainsKeywords(min_match=1)],
        ),
        Case(
            name="irina_kepler9_date_resolved",
            inputs="profile:irina-voss",
            expected_output="2155",
            metadata={"category": "timeline", "difficulty": "hard"},
            evaluators=[BackgroundContainsKeywords(min_match=1)],
        ),
        # hard : la date 2155 n'est plus dans le texte, uniquement "deux ans avant" + scène en 2157
        # le LLM doit calculer 2157 - 2 = 2155 de lui-même
        # --- contradiction physique ---
        Case(
            name="lena_physical_contradiction_detected",
            inputs="issues:scene-05_contradiction",
            expected_output="character_contradiction",
            metadata={"category": "issues", "difficulty": "hard"},
            evaluators=[IssueTypePresent()],
        ),
    ],
)

INGEST_DATASET: Dataset[str, Any] = Dataset(
    cases=[
        # --- scene 001 ---
        Case(
            name="scene1_character_roles",
            inputs="001-la-poussiere.txt",
            expected_output="Jakes Milton:mineur,Mite:drone",
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
        Case(
            name="scene1_no_andrew",
            inputs="001-la-poussiere.txt",
            expected_output="Andrew Milton",
            metadata={"category": "negative", "scene": "001"},
            evaluators=[NoCharacterPresent()],
        ),
        # --- scene 002 ---
        Case(
            name="scene2_character_roles",
            inputs="002-l-orbite.txt",
            expected_output="Andrew Milton:pdg,Jakes:ancetre",
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
        Case(
            name="scene2_no_jakes_participant",
            inputs="002-l-orbite.txt",
            expected_output="Jakes Milton",
            metadata={"category": "negative", "scene": "002"},
            evaluators=[NoCharacterPresent()],
        ),
        # --- test scenes ---
        Case(
            name="test1_all_characters",
            inputs="test-001-le-signal.txt",
            expected_output="Lena Voss,Pixel",
            metadata={"category": "extraction", "scene": "test-001"},
            evaluators=[ExtractsExpectedCharacters()],
        ),
        Case(
            name="test1_era",
            inputs="test-001-le-signal.txt",
            expected_output="2060s",
            metadata={"category": "era", "scene": "test-001"},
            evaluators=[EraAccuracy()],
        ),
        Case(
            name="test1_location",
            inputs="test-001-le-signal.txt",
            expected_output="Helios",
            metadata={"category": "location", "scene": "test-001"},
            evaluators=[LocationAccuracy()],
        ),
        Case(
            name="test2_all_characters",
            inputs="test-002-le-convoi.txt",
            expected_output="Marco Ruiz,Lena Voss",
            metadata={"category": "extraction", "scene": "test-002"},
            evaluators=[ExtractsExpectedCharacters()],
        ),
        Case(
            name="test2_no_pixel",
            inputs="test-002-le-convoi.txt",
            expected_output="Pixel",
            metadata={"category": "negative", "scene": "test-002"},
            evaluators=[NoCharacterPresent()],
        ),
        Case(
            name="test3_all_characters",
            inputs="test-003-la-frequence.txt",
            expected_output="Milton,Voss",
            metadata={"category": "extraction", "scene": "test-003"},
            evaluators=[ExtractsExpectedCharacters()],
        ),
    ],
)

CHATBOT_DATASET: Dataset[str, Any] = Dataset(
    cases=[
        # --- lookup ---
        Case(
            name="lookup_character",
            inputs="Qui est Marie Dupont ?",
            expected_output="Marie, Resistance, 1940s, coursiere",
            metadata={"category": "lookup"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="lookup_pierre",
            inputs="Qui est Pierre Renard ?",
            expected_output="Pierre, Renard, arret, 1942",
            metadata={"category": "lookup"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="lookup_location",
            inputs="Decris la planque de Lyon.",
            expected_output="Planque de Lyon, Lyon, Resistance",
            metadata={"category": "lookup"},
            evaluators=[ContainsExpectedFacts()],
        ),
        # --- coherence ---
        Case(
            name="coherence_marie_sarah",
            inputs="Est-ce coherent si Marie rencontre Sarah en mars 1942 ?",
            expected_output="Sarah, mars 1942, Lyon",
            metadata={"category": "coherence"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="coherence_pierre_november",
            inputs="Ou etait Pierre en novembre 1942 ?",
            expected_output="Pierre, novembre 1942, arret",
            metadata={"category": "coherence"},
            evaluators=[ContainsExpectedFacts()],
        ),
        # --- semantic ---
        Case(
            name="semantic_identity",
            inputs="Trouve les scenes ou quelqu'un decouvre une identite secrete.",
            expected_output="042, identite, Laforge",
            metadata={"category": "semantic"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="semantic_archives",
            inputs="Que se passe-t-il dans les archives ?",
            expected_output="Julien, Paris, document",
            metadata={"category": "semantic"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="semantic_rafle",
            inputs="Trouve les scenes liees aux rafles.",
            expected_output="rafle, Vichy, 1942",
            metadata={"category": "semantic"},
            evaluators=[ContainsExpectedFacts()],
        ),
        # --- cross-era ---
        Case(
            name="cross_era_benoit_julien",
            inputs="Quel est le lien entre Benoit dans les annees 40 et les documents que Julien trouve ?",
            expected_output="Benoit, calendrier, rafle, Julien, documents",
            metadata={"category": "cross_era"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="cross_era_marie_timeline",
            inputs="Quel etait le role de Marie entre janvier et novembre 1942 ?",
            expected_output="Marie, 1942, coursiere, cellule",
            metadata={"category": "cross_era"},
            evaluators=[ContainsExpectedFacts()],
        ),
        # --- causalite ---
        Case(
            name="causal_marie_leader",
            inputs="Qu'est-ce qui a pousse Marie a prendre la tete de la cellule ?",
            expected_output="Pierre est arrete en 1942, Marie prend la tete de la cellule de resistance",
            metadata={"category": "causal"},
            evaluators=[LLMJudge(
                rubric="The response explains that Marie took over the resistance cell following Pierre Renard's arrest in 1942.",
                model=_judge_model,
                include_input=True,
            )],
        ),
        Case(
            name="causal_benoit_protection",
            inputs="Comment les actions de Benoit ont-elles protege la cellule de Pierre ?",
            expected_output="Benoit transmet des informations a Pierre pour proteger la cellule de resistance",
            metadata={"category": "causal"},
            evaluators=[LLMJudge(
                rubric="The response explains that Benoit Laforge, acting as a double agent, transmitted intelligence (schedules, plans) to Pierre Renard's resistance cell.",
                model=_judge_model,
                include_input=True,
            )],
        ),
        Case(
            name="causal_julien_discovery",
            inputs="Pourquoi Julien cherche-t-il dans les archives en 1970 ?",
            expected_output="",
            metadata={"category": "causal"},
            evaluators=[RefusesToFabricate()],
        ),
        Case(
            name="causal_chain_benoit_to_julien",
            inputs="Retrace la chaine causale entre le double jeu de Benoit en 1942 et la decouverte de Julien 30 ans plus tard.",
            expected_output="Benoit transmet en 1942, les documents survivent, Julien les decouvre dans les archives",
            metadata={"category": "causal"},
            evaluators=[LLMJudge(
                rubric="The response traces a causal chain: Benoit's 1942 intelligence transmissions → documents/information preserved → Julien's discovery in archives decades later.",
                model=_judge_model,
                include_input=True,
            )],
        ),
        # --- negative ---
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
        Case(
            name="negative_unknown_person",
            inputs="Qui est Francois Moreau ?",
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
                "that could have been retrieved from a screenplay bible database. "
                "It does not invent or hallucinate any facts."
            ),
            model=_judge_model,
            include_input=True,
        ),
    ],
)

SUITES: dict[str, tuple[Dataset, Any, str]] = {
    "pipeline": (PIPELINE_DATASET, build_pipeline_task, "Pipeline Eval"),
    "ingest":   (INGEST_DATASET,   analyze_scene_task,   "Ingest Eval"),
    "chatbot":  (CHATBOT_DATASET,  felix_task,           "Chat Agent Eval"),
}

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(rich_markup_mode="rich")


@app.command()
def main(
    suite: Annotated[str | None, typer.Option("--suite", help=f"Suite to run: {', '.join(SUITES)}")] = None,
    local: Annotated[bool, typer.Option("--local", help="Use LMStudio local model")] = False,
    openrouter: Annotated[bool, typer.Option("--openrouter", help="Use OpenRouter (reads OPEN_ROUTER key)")] = False,
    together: Annotated[bool, typer.Option("--together", help="Use Together AI (reads TOGETHER_API_KEY)")] = False,
    model: Annotated[str | None, typer.Option("--model", help="Model name override")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="OpenAI-compatible base URL")] = None,
    list_cases: Annotated[bool, typer.Option("--list", help="List cases for the suite and exit")] = False,
    case: Annotated[str | None, typer.Option("--case", help="Run only this case (requires --suite)")] = None,
) -> None:
    """[bold cyan]Felix[/bold cyan] — eval runner."""
    if suite and suite not in SUITES:
        console.print(f"[red]Unknown suite '{suite}'.[/red] Available: {', '.join(SUITES)}")
        raise typer.Exit(1)

    suites_to_run = {suite: SUITES[suite]} if suite else SUITES

    if list_cases:
        for suite_name, (ds, _, title) in suites_to_run.items():
            table = Table(title=title, show_header=True, header_style="bold magenta")
            table.add_column("Name", style="cyan")
            table.add_column("Category", style="yellow")
            table.add_column("Input", style="dim")
            for c in ds.cases:
                cat = (c.metadata or {}).get("category", "")
                table.add_row(c.name, str(cat), str(c.inputs)[:60])
            console.print(table)
        raise typer.Exit()

    model_name, provider = setup_model_env(
        local=local, openrouter=openrouter, together=together, model=model, base_url=base_url
    )
    console.print(Panel(
        f"[bold]Model:[/bold] {model_name}\n[bold]Provider:[/bold] {provider}",
        title="[bold cyan]Felix Evals[/bold cyan]",
        border_style="cyan",
    ))

    for suite_name, (ds, task_fn, title) in suites_to_run.items():
        if len(suites_to_run) > 1:
            console.print(Rule(f"[bold]{title}[/bold]"))

        if case:
            if not suite:
                console.print("[red]--case requires --suite[/red]")
                raise typer.Exit(1)
            cases = [c for c in ds.cases if c.name == case]
            if not cases:
                console.print(f"[red]Case '{case}' not found.[/red] Use [cyan]--list[/cyan] to see available cases.")
                raise typer.Exit(1)
            active_ds = ds.__class__(cases=cases)
        else:
            active_ds = ds

        run_with_spinners(active_ds, task_fn, report_name=suite_name)

    # Force exit: chromadb/sentence-transformers leave non-daemon threads
    # that block normal SystemExit cleanup in CLI eval context.
    os._exit(0)


if __name__ == "__main__":
    app()
