"""Évolution PURE du profil (Étape 4) — PromoteVerbs ajoute/étend un RelationSpec,
MergeTypes renomme partout (entity_types + relation_vocabulary).

Univers de TEST : presse à balles BX-9 (cf. [[feedback_prompt_test_leakage]]).
Aucun accès Neo4j — ``evolve_profile`` est pure, testée sur des ``ChangeReport``
construits à la main.
"""

from __future__ import annotations

from protest import ProTestSuite

from felix.core.profile import EMERGENT_SEED_PROFILE, EntityType, Profile, RelationSpec
from felix.core.profile_evolution import evolve_profile
from felix.core.schema_changes import ChangeReport, MergeTypes, PromoteVerbs

profile_evolution_suite = ProTestSuite("ProfileEvolution")


# ──────────────────── PromoteVerbs : création ────────────────────


@profile_evolution_suite.test()
def test_promote_creates_new_relation_spec_on_seed_profile() -> None:
    change = PromoteVerbs(verbe_slugs=["regle", "pilote"], rel_type="CONTROLS")
    report = ChangeReport(
        change=change,
        observed_pairs=[("commande", "organe"), ("commande", "parametre")],
        verbes=["règle", "pilote"],
    )
    evolved = evolve_profile(EMERGENT_SEED_PROFILE, change, report)

    assert len(evolved.relation_vocabulary) == 1
    spec = evolved.relation_vocabulary[0]
    assert spec.name == "CONTROLS"
    assert spec.gloss == "règle"
    assert spec.subjects == ("commande",)
    assert spec.objects == ("organe", "parametre")
    assert spec.examples == "règle, pilote"


@profile_evolution_suite.test()
def test_promote_does_not_mutate_original_profile() -> None:
    change = PromoteVerbs(verbe_slugs=["regle"], rel_type="CONTROLS")
    report = ChangeReport(
        change=change,
        observed_pairs=[("commande", "organe")],
        verbes=["règle"],
    )
    evolve_profile(EMERGENT_SEED_PROFILE, change, report)
    assert EMERGENT_SEED_PROFILE.relation_vocabulary == ()


@profile_evolution_suite.test()
def test_promote_on_populated_profile_appends_new_spec() -> None:
    base = Profile(
        name="test",
        description="",
        entity_types=(),
        relation_vocabulary=(RelationSpec("PART_OF", "fait partie de"),),
        narrative_rel="LIE_A",
    )
    change = PromoteVerbs(verbe_slugs=["indique"], rel_type="INDICATES")
    report = ChangeReport(
        change=change,
        observed_pairs=[("commande", "mode")],
        verbes=["indique"],
    )
    evolved = evolve_profile(base, change, report)

    names = [s.name for s in evolved.relation_vocabulary]
    assert names == ["PART_OF", "INDICATES"]


# ──────────────────── PromoteVerbs : extension ────────────────────


@profile_evolution_suite.test()
def test_promote_extends_existing_spec_unions_subjects_and_objects() -> None:
    base = Profile(
        name="test",
        description="",
        entity_types=(),
        relation_vocabulary=(
            RelationSpec(
                "CONTROLS",
                "pilote",
                subjects=("commande",),
                objects=("organe",),
                examples="règle",
            ),
        ),
        narrative_rel="LIE_A",
    )
    change = PromoteVerbs(verbe_slugs=["regule"], rel_type="CONTROLS")
    report = ChangeReport(
        change=change,
        observed_pairs=[("mode", "parametre")],
        verbes=["régule"],
    )
    evolved = evolve_profile(base, change, report)

    assert len(evolved.relation_vocabulary) == 1
    spec = evolved.relation_vocabulary[0]
    assert spec.subjects == ("commande", "mode")
    assert spec.objects == ("organe", "parametre")
    assert spec.gloss == "pilote", "la glose d'origine ne bouge pas sur extension"
    assert spec.examples == "règle, régule"


@profile_evolution_suite.test()
def test_promote_extends_does_not_duplicate_known_verb() -> None:
    base = Profile(
        name="test",
        description="",
        entity_types=(),
        relation_vocabulary=(
            RelationSpec(
                "CONTROLS",
                "pilote",
                subjects=("commande",),
                objects=("organe",),
                examples="règle, pilote",
            ),
        ),
        narrative_rel="LIE_A",
    )
    change = PromoteVerbs(verbe_slugs=["regle"], rel_type="CONTROLS")
    report = ChangeReport(
        change=change,
        observed_pairs=[("commande", "organe")],
        verbes=["règle"],
    )
    evolved = evolve_profile(base, change, report)
    assert evolved.relation_vocabulary[0].examples == "règle, pilote"


# ──────────────────── MergeTypes ────────────────────


@profile_evolution_suite.test()
def test_merge_renames_entity_type() -> None:
    base = Profile(
        name="test",
        description="",
        entity_types=(EntityType("piston", ("diametre",)),),
    )
    change = MergeTypes(sources=["piston"], target="organe")
    report = ChangeReport(change=change, entities_retyped=1)
    evolved = evolve_profile(base, change, report)

    assert [et.name for et in evolved.entity_types] == ["organe"]
    assert evolved.entity_types[0].keys == ("diametre",)


@profile_evolution_suite.test()
def test_merge_collapses_source_into_existing_target_union_keys() -> None:
    base = Profile(
        name="test",
        description="",
        entity_types=(
            EntityType("organe", ("fonction",), "note organe"),
            EntityType("piston", ("diametre",)),
        ),
    )
    change = MergeTypes(sources=["piston"], target="organe")
    report = ChangeReport(change=change, entities_retyped=1)
    evolved = evolve_profile(base, change, report)

    assert len(evolved.entity_types) == 1
    merged = evolved.entity_types[0]
    assert merged.name == "organe"
    assert merged.keys == ("fonction", "diametre")
    assert merged.note == "note organe"


@profile_evolution_suite.test()
def test_merge_renames_type_everywhere_in_relation_vocabulary() -> None:
    base = Profile(
        name="test",
        description="",
        entity_types=(EntityType("piston", ()),),
        relation_vocabulary=(
            RelationSpec(
                "CONTROLS", "pilote", subjects=("commande",), objects=("piston", "mode")
            ),
            RelationSpec(
                "PART_OF", "fait partie de", subjects=("piston",), objects=("piston",)
            ),
        ),
    )
    change = MergeTypes(sources=["piston"], target="organe")
    report = ChangeReport(change=change, entities_retyped=1)
    evolved = evolve_profile(base, change, report)

    controls = next(s for s in evolved.relation_vocabulary if s.name == "CONTROLS")
    part_of = next(s for s in evolved.relation_vocabulary if s.name == "PART_OF")
    assert controls.objects == ("organe", "mode")
    assert part_of.subjects == ("organe",)
    assert part_of.objects == ("organe",)


@profile_evolution_suite.test()
def test_merge_leaves_untouched_types_unchanged() -> None:
    base = Profile(
        name="test",
        description="",
        entity_types=(EntityType("commande", ("role",)), EntityType("piston", ())),
    )
    change = MergeTypes(sources=["piston"], target="organe")
    report = ChangeReport(change=change, entities_retyped=1)
    evolved = evolve_profile(base, change, report)

    names = {et.name for et in evolved.entity_types}
    assert names == {"commande", "organe"}
