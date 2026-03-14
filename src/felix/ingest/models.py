from __future__ import annotations

from pydantic import BaseModel


class ExtractedCharacter(BaseModel):
    name: str
    role: str  # "participant" | "witness" | "mentioned"
    description: str | None = None


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


class CharacterProfile(BaseModel):
    age: str | None = None
    physical: str | None = None
    background: str | None = None
    arc: str | None = None
    traits: str | None = None


class ConsistencyIssue(BaseModel):
    type: str  # "timeline_inconsistency" | "character_contradiction" | "missing_info"
    severity: str  # "error" | "warning"
    scene_id: str
    entity_id: str | None = None
    description: str
    suggestion: str


class ConsistencyReport(BaseModel):
    issues: list[ConsistencyIssue]
