"""Evaluateurs heuristiques — rapides, sans LLM.

Ces tests consomment le pipeline_export de conftest.py (session fixture).
Ils mesurent la qualite structurelle du stockage : scenes, personnages,
fragments, timeline, issues, profils, relations.
"""
from __future__ import annotations

from evals.evaluators import (
    eval_characters_found,
    eval_irina_fragments,
    eval_issue_detected,
    eval_profile_grounded,
    eval_relations_present,
    eval_scenes_stored,
    eval_timeline_populated,
    print_report,
    run_all,
)


def test_report(pipeline_export: dict) -> None:
    """Affiche le rapport complet — toujours passe, sert de diagnostic."""
    results = run_all(pipeline_export)
    print_report(results)


def test_scenes_stored(pipeline_export: dict) -> None:
    r = eval_scenes_stored(pipeline_export)
    assert r.passed, r.details


def test_characters_found(pipeline_export: dict) -> None:
    r = eval_characters_found(pipeline_export)
    assert r.score >= 0.75, (  # accepte 3/4 minimum
        f"Trop peu de personnages trouves : {r.details}"
    )


def test_irina_in_all_scenes(pipeline_export: dict) -> None:
    r = eval_irina_fragments(pipeline_export)
    assert r.passed, r.details


def test_timeline_populated(pipeline_export: dict) -> None:
    r = eval_timeline_populated(pipeline_export)
    assert r.passed, r.details


def test_issue_detected(pipeline_export: dict) -> None:
    """La contradiction de Yuna (scene 3) doit etre detectee par le checker."""
    r = eval_issue_detected(pipeline_export)
    assert r.passed, (
        f"Le checker n'a pas detecte la contradiction narrative : {r.details}"
    )


def test_profile_grounded(pipeline_export: dict) -> None:
    """Le background d'Irina doit refleter sa carriere mentionnee en scene 2."""
    r = eval_profile_grounded(pipeline_export)
    assert r.passed, r.details


def test_relations_present(pipeline_export: dict) -> None:
    r = eval_relations_present(pipeline_export)
    assert r.passed, r.details
