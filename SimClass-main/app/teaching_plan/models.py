"""TeachingPlanInput —— 上游教案 JSON 的输入 Schema（Pydantic v2）。"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


def _coerce_str(v):
    if v is None:
        return v
    return str(v)


class TeachingPlanInput(BaseModel):
    materialId: str
    title: str
    teachingScript: str
    keyPoints: list[str] = Field(default_factory=list)
    sourceSectionId: str | None = None
    metadata: dict = Field(default_factory=dict)

    _material_id = field_validator("materialId", mode="before")(_coerce_str)
    _source_section_id = field_validator("sourceSectionId", mode="before")(_coerce_str)

    @field_validator("teachingScript")
    @classmethod
    def _script_must_be_nonempty_str(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("teachingScript 必须是非空字符串（真实教案的教学过程内容）")
        return v
