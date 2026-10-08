from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class SessionStatus(str, Enum):
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    COMPLETED = "COMPLETED"
    INTERRUPTED = "INTERRUPTED"
    FAILED = "FAILED"


class ModelMode(str, Enum):
    REAL = "REAL"
    MOCK = "MOCK"


class MaterialInput(BaseModel):
    """Adapter-friendly material contract.

    Accepts both the formal camelCase fields and the existing SimClass/F4 snake_case
    shape, then serializes to the formal contract.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    material_id: str = Field(
        validation_alias=AliasChoices("materialId", "material_id", "id"),
        serialization_alias="materialId",
        min_length=1,
    )
    title: str = Field(min_length=1)
    teaching_script: str = Field(
        validation_alias=AliasChoices("teachingScript", "teaching_script"),
        serialization_alias="teachingScript",
        min_length=1,
    )
    key_points: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("keyPoints", "key_points"),
        serialization_alias="keyPoints",
    )
    source_section_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("sourceSectionId", "source_section_id"),
        serialization_alias="sourceSectionId",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_classroom_material(self) -> dict[str, Any]:
        # Keep legacy keys because BaseAgent/ClassState read them directly.
        return {
            "id": self.material_id,
            "materialId": self.material_id,
            "title": self.title,
            "teaching_script": self.teaching_script,
            "teachingScript": self.teaching_script,
            "key_points": list(self.key_points),
            "keyPoints": list(self.key_points),
            "sourceSectionId": self.source_section_id,
            "metadata": dict(self.metadata),
        }


class SessionLimits(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    max_events: int = Field(default=60, alias="maxEvents", ge=1, le=1000)
    max_wall_clock_seconds: int = Field(
        default=900, alias="maxWallClockSeconds", ge=1, le=86400
    )
    max_consecutive_timeouts: int = Field(
        default=3, alias="maxConsecutiveTimeouts", ge=1, le=100
    )
    timeout_seconds: float = Field(default=15.0, alias="timeoutSeconds", ge=0.01, le=3600)


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    lesson_id: str = Field(alias="lessonId", min_length=1)
    version_id: str = Field(alias="versionId", min_length=1)
    materials: list[MaterialInput] = Field(min_length=1)
    model_mode: ModelMode | None = Field(default=None, alias="modelMode")
    timeout_seconds: float = Field(default=15.0, alias="timeoutSeconds", ge=0.01, le=3600)
    max_consecutive_timeouts: int = Field(
        default=3, alias="maxConsecutiveTimeouts", ge=1, le=100
    )
    max_events: int = Field(default=60, alias="maxEvents", ge=1, le=1000)
    max_wall_clock_seconds: int = Field(
        default=900, alias="maxWallClockSeconds", ge=1, le=86400
    )
    request_key: str = Field(alias="requestKey", min_length=1, max_length=200)
    source: dict[str, Any] | None = None
    active_roles: list[str] | None = Field(default=None, alias="activeRoles")

    @field_validator("active_roles")
    @classmethod
    def validate_active_roles(cls, value: list[str] | None):
        if not value:
            return value
        known = {"teacher", "assistant", "class_clown", "deep_thinker",
                 "note_taker", "inquisitive_mind"}
        unknown = [role for role in value if role not in known]
        if unknown:
            raise ValueError(f"未知课堂角色: {unknown}")
        if "teacher" not in value:
            raise ValueError("activeRoles 必须包含 teacher")
        # 去重但保持用户传入顺序；Classroom 会再按注册顺序规范化。
        return list(dict.fromkeys(value))

    def limits(self) -> SessionLimits:
        return SessionLimits(
            maxEvents=self.max_events,
            maxWallClockSeconds=self.max_wall_clock_seconds,
            maxConsecutiveTimeouts=self.max_consecutive_timeouts,
            timeoutSeconds=self.timeout_seconds,
        )


class SettingsPatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    timeout_seconds: float | None = Field(
        default=None, alias="timeoutSeconds", ge=0.01, le=3600
    )
    max_consecutive_timeouts: int | None = Field(
        default=None, alias="maxConsecutiveTimeouts", ge=1, le=100
    )
    max_events: int | None = Field(default=None, alias="maxEvents", ge=1, le=1000)
    max_wall_clock_seconds: int | None = Field(
        default=None, alias="maxWallClockSeconds", ge=1, le=86400
    )

    @field_validator("timeout_seconds", "max_consecutive_timeouts", "max_events", "max_wall_clock_seconds")
    @classmethod
    def reject_null_patch(cls, value):
        # Explicit null would silently mean "unchanged"; that is acceptable and
        # friendlier to generated clients, so just pass it through.
        return value
