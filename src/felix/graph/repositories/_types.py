"""TypedDict definitions for repository return types."""
from __future__ import annotations

from typing import TypedDict

# --- Characters ---

class CharacterSummaryRow(TypedDict):
    id: str
    name: str
    era: str


class _CharacterProfileRequired(TypedDict):
    id: str
    name: str
    era: str


class CharacterProfileRow(_CharacterProfileRequired, total=False):
    aliases: list[str]
    age: str
    physical: str
    background: str
    arc: str
    traits: str
    status: str


class RelationRow(TypedDict):
    relation_type: str
    other_name: str
    era: str | None
    description: str | None


class CharacterRelationRow(TypedDict):
    character_id_a: str
    character_id_b: str
    relation_type: str
    description: str | None
    era: str | None


class CharacterFragmentRow(TypedDict):
    scene_id: str
    role: str
    description: str | None
    context: str | None
    scene_title: str | None


class CharacterFragmentExportRow(TypedDict):
    character_id: str
    scene_id: str
    role: str
    description: str | None
    context: str | None


# --- Groups ---

class GroupSummaryRow(TypedDict):
    id: str
    name: str


# --- Locations ---

class SceneInLocationRow(TypedDict):
    id: str
    filename: str
    title: str | None
    era: str | None
    date: str | None


class _LocationRequired(TypedDict):
    id: str
    name: str


class LocationFullRow(_LocationRequired, total=False):
    era: str
    description: str
    address: str
    aliases: list[str]


class LocationDetailRow(_LocationRequired, total=False):
    era: str
    description: str
    address: str
    aliases: list[str]
    scenes: list[SceneInLocationRow]


# --- Scenes ---

class SceneSummaryRow(TypedDict):
    id: str
    filename: str
    title: str | None
    era: str | None
    date: str | None


class SceneWithSummaryRow(TypedDict):
    id: str
    title: str | None
    summary: str | None
    era: str | None
    date: str | None
    location_id: str | None


class _SceneFullRequired(TypedDict):
    id: str
    filename: str


class SceneFullRow(_SceneFullRequired, total=False):
    title: str
    summary: str
    era: str
    date: str
    raw_text: str
    location_id: str


# --- Timeline ---

class TimelineCharacterRow(TypedDict):
    id: str
    name: str


class TimelineRow(TypedDict):
    id: str
    date: str
    era: str
    title: str
    description: str
    location: str
    location_id: str | None
    characters: str
    characters_detail: list[TimelineCharacterRow]


class _TimelineEventRequired(TypedDict):
    id: str
    date: str
    era: str
    title: str


class TimelineEventFullRow(_TimelineEventRequired, total=False):
    description: str
    location_id: str
    scene_id: str


# --- Issues ---

class _IssueRowRequired(TypedDict):
    id: str
    type: str
    severity: str
    description: str
    resolved: bool
    scene_id: str | None


class IssueRow(_IssueRowRequired, total=False):
    entity_id: str | None
    suggestion: str | None
    created_at: str


# --- Beats ---

class NarrativeBeatRow(TypedDict):
    id: str
    action: str
    scene_id: str
    subject_id: str | None
    subject_name: str | None
    object_id: str | None
    object_name: str | None
