"""Ingest eval dataset — scene analyzer isolation tests."""

from __future__ import annotations

from typing import Any

from pydantic_evals import Case, Dataset

from evals.ingest.evaluators import (
    CharacterDescriptionContains,
    CharacterRoleAccuracy,
    EraAccuracy,
    ExtractsExpectedCharacters,
    LocationAccuracy,
    NoCharacterPresent,
    NoEphemeralPhysicalDescription,
)

INGEST_DATASET: Dataset[str, Any] = Dataset(
    name="ingest",
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
            expected_output="Pit 72",
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
