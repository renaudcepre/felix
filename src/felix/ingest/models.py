from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ExtractedCharacter(BaseModel):
    name: str
    role: Literal["participant", "witness", "mentioned"]
    description: str | None = None
    character_type: Literal["individual", "group"] = "individual"


class ExtractedLocation(BaseModel):
    name: str
    description: str | None = None


class SceneAnalysis(BaseModel):
    title: str
    summary: str
    era: str
    approximate_date: str | None = None
    characters: list[ExtractedCharacter]
    location: ExtractedLocation
    mood: str | None = None


class ExtractedRelation(BaseModel):
    other_name: str
    relation: str


class CharacterProfile(BaseModel):
    age: str | None = None
    physical: str | None = None
    background: str | None = None
    arc: str | None = None
    traits: str | None = None
    relations: list[ExtractedRelation] = []


class NarrativeBeat(BaseModel):
    subject: str
    action: str
    object: str | None = None


class ConsistencyIssue(BaseModel):
    type: str  # "timeline_inconsistency" | "character_contradiction" | "missing_info"
    severity: str  # "error" | "warning"
    scene_id: str
    entity_id: str | None = None
    description: str
    suggestion: str


class ConsistencyReport(BaseModel):
    issues: list[ConsistencyIssue]
