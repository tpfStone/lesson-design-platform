from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TriggerRecord(BaseModel):
    type: str
    content: str | None = None


class ManagerDecisionRecord(BaseModel):
    speaker: str
    function: str
    reason: str = ""
    end_class: bool = Field(default=False, alias="endClass")

    model_config = ConfigDict(populate_by_name=True)


class MaterialRef(BaseModel):
    material_id: str = Field(alias="materialId")
    title: str
    source_section_id: str | None = Field(default=None, alias="sourceSectionId")

    model_config = ConfigDict(populate_by_name=True)


class ClassroomEventRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(alias="eventId")
    sequence: int = Field(ge=1)
    session_id: str = Field(alias="sessionId")
    occurred_at: str = Field(alias="occurredAt")
    completed_at: str = Field(alias="completedAt")
    wall_clock_duration_ms: int = Field(alias="wallClockDurationMs", ge=0)
    estimated_teaching_seconds: int | None = Field(
        default=None, alias="estimatedTeachingSeconds"
    )
    estimated: bool = False
    trigger: TriggerRecord
    manager_decision: ManagerDecisionRecord | None = Field(
        default=None, alias="managerDecision"
    )
    speaker: str | None = None
    role_label: str | None = Field(default=None, alias="roleLabel")
    function: str | None = None
    content: str = ""
    material: MaterialRef | None = None
    status: Literal["COMPLETED", "SKIPPED", "FAILED"] = "COMPLETED"
    error: str | None = None
