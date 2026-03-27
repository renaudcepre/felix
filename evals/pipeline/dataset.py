"""Pipeline eval dataset — unified fixture (Thornwall Keep scenario).

Characters: Borin (blacksmith 52), Elara (spy), Darya (herbalist 30),
  Maren (archivist 20), ORACLE (AI mechanism), Sentinels (group)
  + Daria Kovacs, Finn Osei, Luno (from long_mission for segmentation)
"""

from __future__ import annotations

from typing import Any

from pydantic_evals import Case, Dataset

from evals.pipeline.evaluators import (
    BackgroundContainsKeywords,
    CharacterAbsent,
    CharacterIdsPresent,
    EntityCheckHasIssueType,
    EntityCheckNoIssues,
    GroupIdsPresent,
    IssueTypePresent,
    LocationContainsKeyword,
    MinChunkCount,
    MinFragmentCount,
    MinRelationsCount,
    ProfileNotContainsKeyword,
    RelationWithCharPresent,
    SceneDateContainsKeywords,
)

PIPELINE_DATASET: Dataset[str, Any] = Dataset(
    name="pipeline",
    cases=[
        # --- extraction ---
        Case(
            name="u_character_extraction",
            inputs="characters",
            expected_output="borin-ironfist,elara-nightshade,darya,maren-cole",
            metadata={"category": "extraction"},
            evaluators=[CharacterIdsPresent()],
        ),
        Case(
            name="u_oracle_extracted",
            inputs="characters",
            expected_output="oracle",
            metadata={"category": "extraction"},
            evaluators=[CharacterIdsPresent()],
        ),
        Case(
            name="u_sentinels_is_group",
            inputs="groups",
            expected_output="sentinel",
            metadata={"category": "extraction", "tags": ["groups"]},
            evaluators=[GroupIdsPresent()],
        ),
        Case(
            name="u_sentinels_not_individual",
            inputs="characters",
            expected_output="sentinel",
            metadata={"category": "extraction", "tags": ["groups", "negative"]},
            evaluators=[CharacterAbsent()],
        ),
        Case(
            name="u_location_thornwall",
            inputs="locations",
            expected_output="thornwall",
            metadata={"category": "extraction"},
            evaluators=[LocationContainsKeyword()],
        ),
        # --- profiling ---
        Case(
            name="u_borin_profile",
            inputs="profile:borin-ironfist",
            expected_output="blacksmith,smith,forge,mountain,hammer",
            metadata={"category": "profiling"},
            evaluators=[BackgroundContainsKeywords(min_match=2)],
        ),
        Case(
            name="u_borin_has_age",
            inputs="profile:borin-ironfist",
            expected_output="fifty-two,52",
            metadata={"category": "profiling"},
            evaluators=[BackgroundContainsKeywords(min_match=1)],
        ),
        Case(
            name="u_elara_profile",
            inputs="profile:elara-nightshade",
            expected_output="spy,silent,hand,ashford,intelligence",
            metadata={"category": "profiling"},
            evaluators=[BackgroundContainsKeywords(min_match=2)],
        ),
        Case(
            name="u_darya_profile",
            inputs="profile:darya",
            expected_output="herbalist,itinerant,nightshade,wound,satchel",
            metadata={"category": "profiling"},
            evaluators=[BackgroundContainsKeywords(min_match=2)],
        ),
        Case(
            name="u_darya_has_age",
            inputs="profile:darya",
            expected_output="thirty,30",
            metadata={"category": "profiling"},
            evaluators=[BackgroundContainsKeywords(min_match=1)],
        ),
        Case(
            name="u_maren_profile",
            inputs="profile:maren-cole",
            expected_output="archivist,archive,diary,tomlin,tunnel",
            metadata={"category": "profiling"},
            evaluators=[BackgroundContainsKeywords(min_match=2)],
        ),
        Case(
            name="u_maren_age_twenty",
            inputs="profile:maren-cole",
            expected_output="twenty,20",
            metadata={"category": "profiling"},
            evaluators=[BackgroundContainsKeywords(min_match=1)],
        ),
        # --- attribution (negative) ---
        Case(
            name="u_borin_not_spy",
            inputs="profile:borin-ironfist",
            expected_output="spy,silent hand,ashford,intelligence",
            metadata={"category": "attribution", "tags": ["attribution"]},
            evaluators=[ProfileNotContainsKeyword()],
        ),
        Case(
            name="u_darya_not_blacksmith",
            inputs="profile:darya",
            expected_output="blacksmith,anvil,rivet,breastplate",
            metadata={"category": "attribution", "tags": ["attribution"]},
            evaluators=[ProfileNotContainsKeyword()],
        ),
        Case(
            name="u_maren_not_herbalist",
            inputs="profile:maren-cole",
            expected_output="herbalist,nightshade,wound,satchel",
            metadata={"category": "attribution", "tags": ["attribution"]},
            evaluators=[ProfileNotContainsKeyword()],
        ),
        Case(
            name="u_elara_not_blacksmith",
            inputs="profile:elara-nightshade",
            expected_output="blacksmith,anvil,rivet,breastplate",
            metadata={"category": "attribution", "tags": ["attribution"]},
            evaluators=[ProfileNotContainsKeyword()],
        ),
        # --- no-pipe formatting ---
        Case(
            name="u_borin_traits_no_pipe",
            inputs="profile:borin-ironfist",
            expected_output="|",
            metadata={"category": "formatting", "tags": ["no-pipe"]},
            evaluators=[ProfileNotContainsKeyword()],
        ),
        Case(
            name="u_elara_arc_no_pipe",
            inputs="profile:elara-nightshade",
            expected_output="|",
            metadata={"category": "formatting", "tags": ["no-pipe"]},
            evaluators=[ProfileNotContainsKeyword()],
        ),
        # --- appearances ---
        Case(
            name="u_borin_in_both_scenes",
            inputs="fragments:borin-ironfist",
            expected_output="2",
            metadata={"category": "appearances"},
            evaluators=[MinFragmentCount()],
        ),
        Case(
            name="u_darya_in_both_scenes",
            inputs="fragments:darya",
            expected_output="2",
            metadata={"category": "appearances"},
            evaluators=[MinFragmentCount()],
        ),
        Case(
            name="u_maren_in_both_scenes",
            inputs="fragments:maren-cole",
            expected_output="2",
            metadata={"category": "appearances"},
            evaluators=[MinFragmentCount()],
        ),
        # --- relations ---
        Case(
            name="u_has_relations",
            inputs="relations",
            expected_output="3",
            metadata={"category": "relations"},
            evaluators=[MinRelationsCount()],
        ),
        Case(
            name="u_elara_borin_relation",
            inputs="relations:borin-ironfist",
            expected_output="elara",
            metadata={"category": "relations"},
            evaluators=[RelationWithCharPresent()],
        ),
        Case(
            name="u_darya_borin_relation",
            inputs="relations:borin-ironfist",
            expected_output="darya",
            metadata={"category": "relations"},
            evaluators=[RelationWithCharPresent()],
        ),
        # --- dates ---
        Case(
            name="u_scene1_date_1247",
            inputs="scene_date:scene-01_the_forge",
            expected_output="1247",
            metadata={"category": "dates"},
            evaluators=[SceneDateContainsKeywords()],
        ),
        Case(
            name="u_scene2_date_1247",
            inputs="scene_date:scene-02_the_breach",
            expected_output="1247",
            metadata={"category": "dates"},
            evaluators=[SceneDateContainsKeywords()],
        ),
        # --- physical contradiction (polar element) ---
        Case(
            name="u_elara_physical_contradiction",
            inputs="all_issues",
            expected_output="character_contradiction",
            metadata={"category": "issues", "tags": ["issues", "polar"]},
            evaluators=[IssueTypePresent()],
        ),
        # --- mystery / polar attribution ---
        Case(
            name="u_oracle_second_eye_in_profile",
            inputs="profile:oracle",
            expected_output="second eye,communicator,twin,transmit",
            metadata={"category": "profiling", "tags": ["polar"]},
            evaluators=[BackgroundContainsKeywords(min_match=1)],
        ),
        Case(
            name="u_elara_silent_hand_not_varn",
            inputs="profile:elara-nightshade",
            expected_output="varn,reapers,ironholt",
            metadata={"category": "attribution", "tags": ["polar", "attribution"]},
            evaluators=[ProfileNotContainsKeyword()],
        ),
        # --- segmentation (via 03_long_mission.txt) ---
        Case(
            name="u_seg_chunk_count",
            inputs="chunk_count:03_long_mission",
            expected_output="2",
            metadata={"category": "segmentation"},
            evaluators=[MinChunkCount()],
        ),
        Case(
            name="u_seg_daria_kovacs_extracted",
            inputs="characters",
            expected_output="daria-kovacs",
            metadata={"category": "segmentation"},
            evaluators=[CharacterIdsPresent()],
        ),
        Case(
            name="u_seg_finn_extracted",
            inputs="characters",
            expected_output="finn-osei",
            metadata={"category": "segmentation"},
            evaluators=[CharacterIdsPresent()],
        ),
        Case(
            name="u_seg_luno_extracted",
            inputs="characters",
            expected_output="luno",
            metadata={"category": "segmentation"},
            evaluators=[CharacterIdsPresent()],
        ),
        Case(
            name="u_seg_daria_finn_relation",
            inputs="relations:daria-kovacs",
            expected_output="finn",
            metadata={"category": "segmentation"},
            evaluators=[RelationWithCharPresent()],
        ),
        # --- entity check (consistency checker) ---
        Case(
            name="u_ec_borin_age_contradiction",
            inputs='entity_check:borin-ironfist:{"age":"25 years old"}',
            expected_output="profile_contradiction",
            metadata={"category": "entity_check"},
            evaluators=[EntityCheckHasIssueType()],
        ),
        Case(
            name="u_ec_borin_new_detail",
            inputs='entity_check:borin-ironfist:{"background":"Also a skilled cook"}',
            expected_output="",
            metadata={"category": "entity_check"},
            evaluators=[EntityCheckNoIssues()],
        ),
        Case(
            name="u_ec_borin_additional_skill",
            inputs='entity_check:borin-ironfist:{"traits":"Loyal, protective of his people"}',
            expected_output="",
            metadata={"category": "entity_check"},
            evaluators=[EntityCheckNoIssues()],
        ),
        Case(
            name="u_ec_elara_wrong_role",
            inputs='entity_check:elara-nightshade:{"background":"A farmer who has lived in Thornwall all her life"}',
            expected_output="profile_contradiction",
            metadata={"category": "entity_check"},
            evaluators=[EntityCheckHasIssueType()],
        ),
        Case(
            name="u_ec_darya_plausible",
            inputs='entity_check:darya:{"background":"Grew up traveling between villages"}',
            expected_output="",
            metadata={"category": "entity_check"},
            evaluators=[EntityCheckNoIssues()],
        ),
    ],
)
