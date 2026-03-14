from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, field_validator

if TYPE_CHECKING:
    from datetime import datetime


class CharacterSummary(BaseModel):
    id: str
    name: str
    era: str


class Relation(BaseModel):
    relation_type: str
    other_name: str
    era: str | None = None
    description: str | None = None


class CharacterDetail(BaseModel):
    id: str
    name: str
    aliases: list[str]
    era: str
    age: str | None = None
    physical: str | None = None
    background: str | None = None
    arc: str | None = None
    traits: str | None = None
    status: str | None = None
    relations: list[Relation] = []

    @field_validator("aliases", mode="before")
    @classmethod
    def parse_aliases(cls, v: str | list[str] | None) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return json.loads(v)
        return v


class LocationSummary(BaseModel):
    id: str
    name: str
    era: str | None = None


class LocationDetail(BaseModel):
    id: str
    name: str
    era: str | None = None
    description: str | None = None
    address: str | None = None
    scenes: list[SceneSummary] = []


class TimelineCharacter(BaseModel):
    id: str
    name: str


class TimelineEvent(BaseModel):
    id: str
    date: str
    era: str
    title: str
    description: str = ""
    location: str = ""
    location_id: str | None = None
    characters: str = ""
    characters_detail: list[TimelineCharacter] = []


class Issue(BaseModel):
    id: str
    type: str
    severity: str
    scene_id: str | None = None
    entity_id: str | None = None
    description: str
    suggestion: str | None = None
    resolved: bool = False
    created_at: str | None = None

    @field_validator("resolved", mode="before")
    @classmethod
    def parse_resolved(cls, v: int | bool) -> bool:
        return bool(v)


class IssueUpdate(BaseModel):
    resolved: bool


class ImportProgressResponse(BaseModel):
    status: str
    total_scenes: int = 0
    processed_scenes: int = 0
    current_scene: str = ""
    issues_found: int = 0
    error: str = ""
    new_characters: list[str] = []
    new_locations: list[str] = []


class SceneSummary(BaseModel):
    id: str
    filename: str
    title: str | None = None
    era: str | None = None
    date: str | None = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    message_history: list[dict[str, object]] = []


class UsageInfo(BaseModel):
    request_tokens: int = 0
    response_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    output: str
    message_history: list[dict[str, object]]
    usage: UsageInfo | None = None


# --- Export models ---


class LocationExport(BaseModel):
    id: str
    name: str
    era: str | None = None
    description: str | None = None
    address: str | None = None


class SceneExport(BaseModel):
    id: str
    filename: str
    title: str | None = None
    summary: str | None = None
    era: str | None = None
    date: str | None = None
    location_id: str | None = None
    raw_text: str | None = None


class TimelineEventExport(BaseModel):
    id: str
    date: str
    era: str
    title: str
    description: str | None = None
    location_id: str | None = None
    scene_id: str | None = None


class CharacterEventExport(BaseModel):
    character_id: str
    event_id: str
    role: str | None = None


class CharacterRelationExport(BaseModel):
    character_id_a: str
    character_id_b: str
    relation_type: str
    description: str | None = None
    era: str | None = None


class CharacterFragmentExport(BaseModel):
    character_id: str
    scene_id: str
    role: str | None = None
    description: str | None = None


class FullExport(BaseModel):
    exported_at: datetime
    characters: list[CharacterDetail]
    locations: list[LocationExport]
    scenes: list[SceneExport]
    timeline_events: list[TimelineEventExport]
    character_events: list[CharacterEventExport]
    character_relations: list[CharacterRelationExport]
    character_fragments: list[CharacterFragmentExport]
    issues: list[Issue]
