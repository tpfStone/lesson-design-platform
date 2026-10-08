from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ISSUE_CATEGORIES = {
    "student_misconception",
    "insufficient_explanation",
    "participation_imbalance",
    "interaction_gap",
    "pace_risk",
    "material_transition",
    "assessment_gap",
    "other",
}
SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


class EvidenceRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(alias="eventId")
    sequence: int
    speaker: str
    content_quote: str = Field(alias="contentQuote", min_length=1)


class IssueRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    native_issue_id: str = Field(alias="nativeIssueId")
    category: str
    severity: str
    title: str
    problem: str
    evidence: list[EvidenceRef] = Field(min_length=1)
    resolved_in_simulation: bool = Field(default=False, alias="resolvedInSimulation")
    resolution_evidence_event_ids: list[str] = Field(
        default_factory=list, alias="resolutionEvidenceEventIds"
    )
    resolution: str | None = None
    suggested_action: str = Field(alias="suggestedAction")
    target_lesson_section: str | None = Field(default=None, alias="targetLessonSection")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class AnalysisResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    analysis_schema_version: str = Field(default="1.0", alias="analysisSchemaVersion")
    session_id: str = Field(alias="sessionId")
    source_version_id: str = Field(alias="sourceVersionId")
    model_mode: str | None = Field(default=None, alias="modelMode")
    issues: list[IssueRecord] = Field(default_factory=list)
    action_items: list[dict] = Field(default_factory=list, alias="actionItems")
    warnings: list[str] = Field(default_factory=list)
