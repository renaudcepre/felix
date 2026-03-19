"""Felix eval runner — unified entry point for all eval suites.

Usage:
    uv run python -m evals.run_evals --suite pipeline --together
    uv run python -m evals.run_evals --suite ingest --local
    uv run python -m evals.run_evals --suite pipeline --mistral
    uv run python -m evals.run_evals --suite pipeline --list
    uv run python -m evals.run_evals --suite pipeline --case character_extraction
    uv run python -m evals.run_evals                          # toutes les suites
"""

from __future__ import annotations

import atexit
import os
from typing import Annotated, Any

import logfire
import typer
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.providers.mistral import MistralProvider
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import LLMJudge
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from evals._runner import load_history, run_suite_async, setup_model_env
from evals.evaluators import ContainsExpectedFacts, RefusesToFabricate
from evals.ingest.evaluators import (
    CharacterDescriptionContains,
    CharacterRoleAccuracy,
    EraAccuracy,
    ExtractsExpectedCharacters,
    LocationAccuracy,
    NoCharacterPresent,
    NoEphemeralPhysicalDescription,
)
from evals.ingest.task import analyze_scene_task
from evals.pipeline.evaluators import (
    AllLocationsContainKeyword,
    BackgroundContainsKeywords,
    CharacterAbsent,
    CharacterIdsPresent,
    ExactFragmentCount,
    ExactIssueCountByType,
    IssueDescriptionContains,
    IssueTypeAbsent,
    IssueTypePresent,
    LocationContainsKeyword,
    MaxIssueSeverityCount,
    MinChunkCount,
    MinFragmentCount,
    MinIssueCount,
    MinRelationsCount,
    NoIssueDescriptionContains,
    ProfileNotContainsKeyword,
    RelationWithCharPresent,
    SceneDateContainsKeywords,
)
from evals.pipeline.task import make_pipeline_task
from evals.task import felix_task
from felix.config import settings
from felix.telemetry import setup_logging

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
            name="chen_active_appearances",
            inputs="active_fragments:chen-wei",
            expected_output="2",
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
            evaluators=[SceneDateContainsKeywords()],
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
        # --- déduplication des relations ---
        Case(
            name="no_duplicate_irina_kofi_relation",
            inputs="relation_count:irina-voss,kofi-adu",
            expected_output="1",
            metadata={"category": "relations", "difficulty": "hard"},
            evaluators=[ExactFragmentCount()],
        ),
        # --- contradiction physique ---
        Case(
            name="lena_physical_contradiction_detected",
            inputs="issues:scene-05_contradiction",
            expected_output="character_contradiction",
            metadata={"category": "issues", "difficulty": "hard"},
            evaluators=[IssueTypePresent()],
        ),
        # --- relative date resolution ---
        Case(
            name="reldate_scene07_date_extracted",
            inputs="scene_date:scene-07_reldate",
            expected_output="2157",
            metadata={"category": "relative_date", "difficulty": "easy"},
            evaluators=[SceneDateContainsKeywords()],
        ),
        Case(
            name="reldate_vingt_neuf_in_profile",
            inputs="profile:irina-voss",
            expected_output="vingt-neuf,mois,semaine",
            metadata={"category": "relative_date", "difficulty": "hard"},
            evaluators=[BackgroundContainsKeywords(min_match=1)],
        ),
        # --- no pipe accumulation in traits/arc ---
        Case(
            name="irina_traits_no_pipe",
            inputs="traits:irina-voss",
            expected_output="|",
            metadata={"category": "profiling", "difficulty": "medium"},
            evaluators=[ProfileNotContainsKeyword()],
        ),
        Case(
            name="irina_arc_no_pipe",
            inputs="arc:irina-voss",
            expected_output="|",
            metadata={"category": "profiling", "difficulty": "medium"},
            evaluators=[ProfileNotContainsKeyword()],
        ),
        # --- incremental profile (amnesia) ---
        Case(
            name="amnesia_irina_all_scenes",
            inputs="fragments:irina-voss",
            expected_output="4",
            metadata={"category": "amnesia", "difficulty": "medium"},
            evaluators=[MinFragmentCount()],
        ),
        Case(
            name="amnesia_profile_survives_patching",
            inputs="profile:irina-voss",
            expected_output="DR-7,Kepler",
            metadata={"category": "amnesia", "difficulty": "hard"},
            evaluators=[BackgroundContainsKeywords(min_match=2)],
        ),
    ],
)

CONVOI_DATASET: Dataset[str, Any] = Dataset(
    cases=[
        # --- extraction ---
        Case(
            name="convoi_character_extraction",
            inputs="characters",
            expected_output="marco-ruiz,lena-voss",
            metadata={"category": "extraction"},
            evaluators=[CharacterIdsPresent()],
        ),
        Case(
            name="convoi_pixel_extracted",
            inputs="characters",
            expected_output="pixel",
            metadata={"category": "extraction"},
            evaluators=[CharacterIdsPresent()],
        ),
        # --- appearances ---
        Case(
            name="convoi_lena_in_three_scenes",
            inputs="fragments:lena-voss",
            expected_output="3",
            metadata={"category": "appearances"},
            evaluators=[MinFragmentCount()],
        ),
        Case(
            name="convoi_lena_active_three",
            inputs="active_fragments:lena-voss",
            expected_output="3",
            metadata={"category": "appearances"},
            evaluators=[ExactFragmentCount()],
        ),
        Case(
            name="convoi_marco_appears_once",
            inputs="fragments:marco-ruiz",
            expected_output="1",
            metadata={"category": "appearances"},
            evaluators=[ExactFragmentCount()],
        ),
        # --- timeline ---
        Case(
            name="convoi_scene1_date",
            inputs="scene_date:scene-test-001-le-signal",
            expected_output="2061",
            metadata={"category": "timeline"},
            evaluators=[SceneDateContainsKeywords()],
        ),
        # --- locations ---
        Case(
            name="convoi_helios_location",
            inputs="locations",
            expected_output="helios",
            metadata={"category": "extraction"},
            evaluators=[LocationContainsKeyword()],
        ),
        Case(
            name="convoi_neosantiago_location",
            inputs="locations",
            expected_output="neo",
            metadata={"category": "extraction"},
            evaluators=[LocationContainsKeyword()],
        ),
        # --- consistency (regression tests) ---
        Case(
            name="convoi_bilocalization_exact_count",
            inputs="all_issues",
            expected_output="3",
            metadata={"category": "consistency", "difficulty": "hard"},
            evaluators=[ExactIssueCountByType(issue_type="bilocalization")],
        ),
        Case(
            name="convoi_no_anachronique_issue",
            inputs="all_issues",
            expected_output="anachronique",
            metadata={"category": "consistency", "difficulty": "hard"},
            evaluators=[NoIssueDescriptionContains()],
        ),
        Case(
            name="convoi_lena_in_biloc_desc",
            inputs="all_issues",
            expected_output="lena",
            metadata={"category": "consistency"},
            evaluators=[IssueDescriptionContains()],
        ),
        # --- relations ---
        Case(
            name="convoi_marco_lena_related",
            inputs="relations:lena-voss",
            expected_output="marco-ruiz",
            metadata={"category": "relations"},
            evaluators=[RelationWithCharPresent()],
        ),
    ],
)

SEGMENTATION_DATASET: Dataset[str, Any] = Dataset(
    cases=[
        # --- segmentation structurelle ---
        Case(
            name="seg_chunk_count",
            inputs="chunk_count:long-mission",
            expected_output="2",
            metadata={"category": "segmentation"},
            evaluators=[MinChunkCount()],
        ),
        Case(
            name="seg_next_chunk_links",
            inputs="next_chunk_links:long-mission",
            expected_output="1",
            metadata={"category": "segmentation"},
            evaluators=[MinChunkCount()],
        ),
        # --- extraction malgré le chunking ---
        Case(
            name="seg_characters_extracted",
            inputs="characters",
            expected_output="daria-kovacs,finn-osei",
            metadata={"category": "extraction"},
            evaluators=[CharacterIdsPresent()],
        ),
        Case(
            name="seg_luno_extracted",
            inputs="characters",
            expected_output="luno",
            metadata={"category": "extraction"},
            evaluators=[CharacterIdsPresent()],
        ),
        # --- présence dans plusieurs chunks ---
        Case(
            name="seg_daria_multi_fragments",
            inputs="fragments:daria-kovacs",
            expected_output="2",
            metadata={"category": "segmentation", "difficulty": "medium"},
            evaluators=[MinFragmentCount()],
        ),
        # --- profiling cross-chunk ---
        Case(
            name="seg_daria_profile",
            inputs="profile:daria-kovacs",
            expected_output="ingenieure,aurore",
            metadata={"category": "profiling"},
            evaluators=[BackgroundContainsKeywords(min_match=1)],
        ),
        Case(
            name="seg_finn_profile",
            inputs="profile:finn-osei",
            expected_output="securite,callisto",
            metadata={"category": "profiling"},
            evaluators=[BackgroundContainsKeywords(min_match=1)],
        ),
        # --- extraction de lieu ---
        Case(
            name="seg_location_aurore",
            inputs="locations",
            expected_output="aurore",
            metadata={"category": "extraction"},
            evaluators=[LocationContainsKeyword()],
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
            name="test2_marco_no_ephemeral_physical",
            inputs="test-002-le-convoi.txt",
            expected_output="",
            metadata={"category": "physical_description", "scene": "test-002", "difficulty": "medium"},
            evaluators=[NoEphemeralPhysicalDescription(character="Marco Ruiz")],
        ),
        Case(
            name="test3_all_characters",
            inputs="test-003-la-frequence.txt",
            expected_output="Milton,Voss",
            metadata={"category": "extraction", "scene": "test-003"},
            evaluators=[ExtractsExpectedCharacters()],
        ),
        # --- physical description : ephemeral vs permanent ---
        Case(
            name="ephemeral_haddad_no_redeyes",
            inputs="eval-ephemeral-physical.txt",
            expected_output="",
            metadata={"category": "physical_description", "difficulty": "medium"},
            evaluators=[NoEphemeralPhysicalDescription(character="Karim Haddad")],
        ),
        Case(
            name="ephemeral_haddad_no_anger",
            inputs="eval-ephemeral-physical.txt",
            expected_output="",
            metadata={"category": "physical_description", "difficulty": "medium"},
            evaluators=[NoEphemeralPhysicalDescription(character="Karim Haddad")],
        ),
        Case(
            name="fantasy_varek_redeyes_in_desc",
            inputs="eval-fantasy-redeyes.txt",
            expected_output="rouge,red,crimson",
            metadata={"category": "physical_description", "difficulty": "hard"},
            evaluators=[CharacterDescriptionContains(character="Varek")],
        ),
        Case(
            name="fantasy_varek_extracted",
            inputs="eval-fantasy-redeyes.txt",
            expected_output="Varek,Ilena",
            metadata={"category": "extraction", "difficulty": "easy"},
            evaluators=[ExtractsExpectedCharacters()],
        ),
    ],
)

CHATBOT_DATASET: Dataset[str, Any] = Dataset(
    cases=[
        # --- lookup ---
        Case(
            name="lookup_character",
            inputs="Who is Marie Dupont?",
            expected_output="Marie, Resistance, 1940s, coursiere",
            metadata={"category": "lookup"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="lookup_pierre",
            inputs="Who is Pierre Renard?",
            expected_output="Pierre, Renard, arret, 1942",
            metadata={"category": "lookup"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="lookup_location",
            inputs="Describe the Lyon safehouse.",
            expected_output="Planque de Lyon, Lyon, Resistance",
            metadata={"category": "lookup"},
            evaluators=[ContainsExpectedFacts()],
        ),
        # --- coherence ---
        Case(
            name="coherence_marie_sarah",
            inputs="Is it consistent for Marie to meet Sarah in March 1942?",
            expected_output="Sarah, mars 1942, Lyon",
            metadata={"category": "coherence"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="coherence_pierre_november",
            inputs="Where was Pierre in November 1942?",
            expected_output="Pierre, novembre 1942, arret",
            metadata={"category": "coherence"},
            evaluators=[ContainsExpectedFacts()],
        ),
        # --- semantic ---
        Case(
            name="semantic_identity",
            inputs="Find scenes where someone discovers a secret identity.",
            expected_output="042, identite, Laforge",
            metadata={"category": "semantic"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="semantic_archives",
            inputs="What happens in the archives?",
            expected_output="Julien, Paris, document",
            metadata={"category": "semantic"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="semantic_rafle",
            inputs="Find scenes related to the roundups.",
            expected_output="rafle, Vichy, 1942",
            metadata={"category": "semantic"},
            evaluators=[ContainsExpectedFacts()],
        ),
        # --- cross-era ---
        Case(
            name="cross_era_benoit_julien",
            inputs="What is the connection between Benoit in the 1940s and the documents Julien finds?",
            expected_output="Benoit, calendrier, rafle, Julien, documents",
            metadata={"category": "cross_era"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="cross_era_marie_timeline",
            inputs="What was Marie's role between January and November 1942?",
            expected_output="Marie, 1942, coursiere, cellule",
            metadata={"category": "cross_era"},
            evaluators=[ContainsExpectedFacts()],
        ),
        # --- causalite ---
        Case(
            name="causal_marie_leader",
            inputs="What pushed Marie to take over the cell?",
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
            inputs="How did Benoit's actions protect Pierre's cell?",
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
            inputs="Why is Julien searching the archives in 1970?",
            expected_output="",
            metadata={"category": "causal"},
            evaluators=[RefusesToFabricate()],
        ),
        Case(
            name="causal_chain_benoit_to_julien",
            inputs="Trace the causal chain between Benoit's double game in 1942 and Julien's discovery 30 years later.",
            expected_output="Benoit transmet en 1942, les documents survivent, Julien les decouvre dans les archives",
            metadata={"category": "causal"},
            evaluators=[LLMJudge(
                rubric="The response traces a causal chain: Benoit's 1942 intelligence transmissions → documents/information preserved → Julien's discovery in archives decades later.",
                model=_judge_model,
                include_input=True,
            )],
        ),
        # --- prop tracking (Chekhov's gun) ---
        Case(
            name="prop_carbone_origin",
            inputs="Who created the carbon copy mentioned in the 1942 archives?",
            expected_output="Benoit,calendrier,rafle",
            metadata={"category": "prop_tracking", "difficulty": "medium"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="prop_carbone_rediscovery",
            inputs="When and where does the carbon copy reappear after 1942?",
            expected_output="Julien,1974,archives",
            metadata={"category": "prop_tracking", "difficulty": "medium"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="prop_carbone_full_trace",
            inputs="Trace the roundup document from its creation to its rediscovery.",
            expected_output="Benoit crée le carbone en 1942, Julien le retrouve dans les archives en 1974",
            metadata={"category": "prop_tracking", "difficulty": "hard"},
            evaluators=[LLMJudge(
                rubric="Response traces the document from Benoit's clandestine carbon copy in 1942 to Julien's discovery in the Paris Tribune archives in 1974, identifying Benoit as the origin.",
                model=_judge_model,
                include_input=True,
            )],
        ),
        # --- information asymmetry ---
        Case(
            name="asym_julien_henriblanc",
            inputs="When Julien meets Henri Blanc in June 1974, does he know it's Benoit Laforge?",
            expected_output="Julien ne sait pas que Henri Blanc est Benoit Laforge lors de leur rencontre",
            metadata={"category": "info_asymmetry", "difficulty": "medium"},
            evaluators=[LLMJudge(
                rubric="Response correctly states that Julien does not yet know Henri Blanc is Benoit Laforge at the time of their June 1974 meeting (evt-010 explicitly says he doesn't know yet).",
                model=_judge_model,
                include_input=True,
            )],
        ),
        Case(
            name="asym_marie_benoit_july42",
            inputs="By July 1942, does Marie already know Benoit is a double agent?",
            expected_output="",
            metadata={"category": "info_asymmetry", "difficulty": "hard"},
            evaluators=[RefusesToFabricate()],
        ),
        Case(
            name="asym_who_knows_june42",
            inputs="In June 1942, who knows that Benoit is passing information to the Resistance?",
            expected_output="Pierre,Benoit",
            metadata={"category": "info_asymmetry", "difficulty": "medium"},
            evaluators=[ContainsExpectedFacts()],
        ),
        # --- alias resolution ---
        Case(
            name="alias_inspecteur_laforge",
            inputs="Who is Inspector Laforge?",
            expected_output="Benoit,Laforge,agent double",
            metadata={"category": "alias_resolution", "difficulty": "medium"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="alias_henri_blanc",
            inputs="Who is Henri Blanc?",
            expected_output="Benoit,1974,faux nom",
            metadata={"category": "alias_resolution", "difficulty": "medium"},
            evaluators=[ContainsExpectedFacts()],
        ),
        Case(
            name="alias_le_fantome",
            inputs="Who is Le Fantome?",
            expected_output="",
            metadata={"category": "alias_resolution", "difficulty": "easy"},
            evaluators=[RefusesToFabricate()],
        ),
        # --- negative ---
        Case(
            name="negative_car_color",
            inputs="What color is Marie's car?",
            expected_output="",
            metadata={"category": "negative"},
            evaluators=[RefusesToFabricate()],
        ),
        Case(
            name="negative_julien_brother",
            inputs="Who is Julien's brother?",
            expected_output="",
            metadata={"category": "negative"},
            evaluators=[RefusesToFabricate()],
        ),
        Case(
            name="negative_unknown_person",
            inputs="Who is Francois Moreau?",
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

def _show_history(suite: str | None, *, diff: bool = False) -> None:
    """Display past eval runs or diff the last two."""
    entries = load_history(suite)
    if not entries:
        console.print("[dim]No history yet.[/dim]")
        return

    if diff:
        if len(entries) < 2:
            console.print("[dim]Need at least 2 runs to diff.[/dim]")
            return
        prev, curr = entries[-2], entries[-1]
        table = Table(
            title=f"Diff: {prev['ts']} → {curr['ts']}  ({curr['suite']})",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Case", style="cyan")
        table.add_column("Before")
        table.add_column("After")
        table.add_column("Delta")
        all_cases = dict.fromkeys([*prev["cases"], *curr["cases"]])
        for name in all_cases:
            was = prev["cases"].get(name)
            now = curr["cases"].get(name)
            before_s = "[green]PASS[/green]" if was else ("[red]FAIL[/red]" if was is not None else "[dim]—[/dim]")
            after_s = "[green]PASS[/green]" if now else ("[red]FAIL[/red]" if now is not None else "[dim]—[/dim]")
            if was == now:
                delta = "[dim]=[/dim]"
            elif now and not was:
                delta = "[green]+[/green]"
            elif was and not now:
                delta = "[red]−[/red]"
            else:
                delta = "[yellow]new[/yellow]"
            table.add_row(name, before_s, after_s, delta)
        console.print(table)
        console.print(
            f"\n  {prev['passed']}/{prev['total']} → {curr['passed']}/{curr['total']}"
        )
        return

    table = Table(title="Eval History", show_header=True, header_style="bold magenta")
    table.add_column("Timestamp", style="cyan")
    table.add_column("Suite", style="yellow")
    table.add_column("Model", style="dim")
    table.add_column("Result", justify="right")
    table.add_column("Score", justify="right")
    for e in entries:
        p, t = e["passed"], e["total"]
        pct = p / t * 100 if t else 0
        color = "green" if p == t else "yellow" if pct >= 70 else "red"
        table.add_row(
            e["ts"],
            e["suite"],
            e["model"],
            f"[{color}]{p}/{t}[/{color}]",
            f"[{color}]{pct:.0f}%[/{color}]",
        )
    console.print(table)


PROFILER_ATTRIBUTION_DATASET: Dataset[str, Any] = Dataset(
    cases=[
        # --- extraction ---
        Case(
            name="attr_characters_extracted",
            inputs="characters",
            expected_output="gandalf,aldric,mira",
            metadata={"category": "extraction"},
            evaluators=[CharacterIdsPresent()],
        ),
        # --- attribution correcte : Aldric reçoit la lame Morgul ---
        Case(
            name="attr_aldric_morgul_in_arc",
            inputs="profile:aldric",
            expected_output="morgul,lame,poignard,bless,conscience,blafard,froid,plaie",
            metadata={"category": "profiling", "difficulty": "medium"},
            evaluators=[BackgroundContainsKeywords(min_match=1)],
        ),
        # --- non-attribution : Gandalf NE doit PAS avoir la blessure dans son profil ---
        Case(
            name="attr_gandalf_not_stabbed",
            inputs="profile:gandalf",
            expected_output="morgul,poignard,bless",
            metadata={"category": "profiling", "difficulty": "hard"},
            evaluators=[ProfileNotContainsKeyword()],
        ),
        # --- Gandalf actif dans les 3 scènes ---
        Case(
            name="attr_gandalf_three_scenes",
            inputs="fragments:gandalf",
            expected_output="3",
            metadata={"category": "appearances"},
            evaluators=[MinFragmentCount()],
        ),
        # --- Aldric actif dans les 3 scènes ---
        Case(
            name="attr_aldric_three_scenes",
            inputs="fragments:aldric",
            expected_output="3",
            metadata={"category": "appearances"},
            evaluators=[MinFragmentCount()],
        ),
        # --- no pipe accumulation in traits/arc ---
        Case(
            name="attr_gandalf_traits_no_pipe",
            inputs="traits:gandalf",
            expected_output="|",
            metadata={"category": "profiling", "difficulty": "medium"},
            evaluators=[ProfileNotContainsKeyword()],
        ),
        Case(
            name="attr_aldric_arc_no_pipe",
            inputs="arc:aldric",
            expected_output="|",
            metadata={"category": "profiling", "difficulty": "medium"},
            evaluators=[ProfileNotContainsKeyword()],
        ),
    ],
)

SUITES: dict[str, tuple[Dataset, Any, str]] = {
    "pipeline":                    (PIPELINE_DATASET,              make_pipeline_task("helios"),                "Pipeline Eval (Helios)"),
    "pipeline-convoi":             (CONVOI_DATASET,                make_pipeline_task("convoi"),                "Pipeline Eval (Convoi)"),
    "pipeline-segmentation":       (SEGMENTATION_DATASET,          make_pipeline_task("segmentation"),          "Pipeline Eval (Segmentation)"),
    "pipeline-profiler-attribution": (PROFILER_ATTRIBUTION_DATASET, make_pipeline_task("profiler_attribution"), "Pipeline Eval (Profiler Attribution)"),
    "ingest":                      (INGEST_DATASET,                 analyze_scene_task,                          "Ingest Eval"),
    "chatbot":                     (CHATBOT_DATASET,                felix_task,                                  "Chat Agent Eval"),
}

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(rich_markup_mode="rich")


@app.command()
def main(
    suite: Annotated[str | None, typer.Option("--suite", help=f"Suite to run: {', '.join(SUITES)}")] = None,
    local: Annotated[bool, typer.Option("--local", help="Use LMStudio local model")] = False,
    together: Annotated[bool, typer.Option("--together", help="Use Together AI (reads TOGETHER_API_KEY)")] = False,
    mistral: Annotated[bool, typer.Option("--mistral", help="Use Mistral API (reads FLX_API_KEY)")] = False,
    model: Annotated[str | None, typer.Option("--model", help="Model name override")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="OpenAI-compatible base URL")] = None,
    list_cases: Annotated[bool, typer.Option("--list", help="List cases for the suite and exit")] = False,
    case: Annotated[str | None, typer.Option("--case", help="Run only this case (requires --suite)")] = None,
    history: Annotated[bool, typer.Option("--history", help="Show past run results and exit")] = False,
    diff: Annotated[bool, typer.Option("--diff", help="Compare the last two runs for the suite")] = False,
) -> None:
    """[bold cyan]Felix[/bold cyan] — eval runner."""
    # Registered first → runs last (LIFO): all other atexit handlers execute
    # before this, then os._exit prevents threading._shutdown from hanging
    # on non-daemon threads left by chromadb / sentence-transformers.
    atexit.register(os._exit, 0)

    setup_logging()

    if settings.logfire_token:
        logfire.configure(
            token=settings.logfire_token,
            console={"min_log_level": "warn"},
        )
        logfire.instrument_pydantic_ai(event_mode="logs")

    if history or diff:
        _show_history(suite, diff=diff)
        raise typer.Exit()

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
        local=local, together=together, mistral=mistral, model=model, base_url=base_url
    )
    console.print(Panel(
        f"[bold]Model:[/bold] {model_name}\n[bold]Provider:[/bold] {provider}",
        title="[bold cyan]Felix Evals[/bold cyan]",
        border_style="cyan",
    ))

    import asyncio

    async def _run_all() -> None:
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

            await run_suite_async(active_ds, task_fn, report_name=suite_name)

    asyncio.run(_run_all())
    raise typer.Exit()


if __name__ == "__main__":
    app()
