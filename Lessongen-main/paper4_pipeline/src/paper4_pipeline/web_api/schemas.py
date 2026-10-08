"""Strict internal API contracts shared by the FastAPI facade and workers."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from paper4_pipeline.domain.models import (
    LessonPlanDocument,
    RubricScores,
    StrictModel,
    TokenUsage,
)


class EngineMode(str, Enum):
    GENERATE = "generate"
    OPTIMIZE = "optimize"


class EngineRunStatus(str, Enum):
    QUEUED = "queued"
    PREPROCESSING = "preprocessing"
    RUNNING = "running"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    NEEDS_HUMAN = "needs_human"
    FAILED = "failed"


class EngineLessonInput(StrictModel):
    mode: EngineMode
    subject: str = Field(min_length=1, max_length=64)
    grade: str = Field(min_length=1, max_length=64)
    topic: str = Field(min_length=1, max_length=255)
    duration_minutes: int = Field(default=45, ge=5, le=240)
    course_information: str = Field(default="", max_length=4000)
    textbook_version: str = Field(default="", max_length=255)
    textbook_content: str = Field(default="", max_length=30_000)
    curriculum_standards: list[str] = Field(default_factory=list, max_length=50)
    learning_objectives: list[str] = Field(default_factory=list, max_length=20)
    student_profile: str = Field(default="", max_length=8000)
    class_size: int | None = Field(default=None, ge=1, le=200)
    available_resources: list[str] = Field(default_factory=list, max_length=50)
    additional_requirements: str = Field(default="", max_length=8000)
    lesson_style: str = "choose_the_best_fit_for_this_topic"
    detail_level: Literal["standard", "showcase"] = "showcase"
    optimization_focus: list[str] = Field(default_factory=list, max_length=20)
    must_preserve_content: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_mode_fields(self) -> "EngineLessonInput":
        if self.mode == EngineMode.GENERATE and (
            self.optimization_focus or self.must_preserve_content
        ):
            raise ValueError("generate input cannot contain optimization-only fields")
        return self


class CreateRunRequest(StrictModel):
    contract_version: Literal["1"] = "1"
    external_job_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    task: EngineLessonInput


class RunAccepted(StrictModel):
    engine_run_id: str
    external_job_id: str
    status: EngineRunStatus
    created_at: datetime


class EngineUsage(StrictModel):
    model_call_count: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost: float = Field(default=0, ge=0)


class EngineError(StrictModel):
    code: str
    message: str


class RunSnapshot(StrictModel):
    engine_run_id: str
    external_job_id: str
    status: EngineRunStatus
    stage: str
    round_index: int = Field(default=0, ge=0)
    version_id: str = ""
    progress_percent: int = Field(default=0, ge=0, le=100)
    pipeline_status: str | None = None
    stop_reason: str | None = None
    best_version_id: str | None = None
    last_version_id: str | None = None
    usage: EngineUsage = Field(default_factory=EngineUsage)
    last_event_sequence: int = Field(default=0, ge=0)
    error: EngineError | None = None
    updated_at: datetime


class PublicEngineEvent(StrictModel):
    sequence: int = Field(ge=1)
    event_type: str
    stage: str
    round_index: int = Field(default=0, ge=0)
    version_id: str = ""
    progress_percent: int = Field(ge=0, le=100)
    message: str
    occurred_at: datetime


class EngineEventPage(StrictModel):
    items: list[PublicEngineEvent]
    last_sequence: int = Field(ge=0)
    has_more: bool = False


class EngineArtifact(StrictModel):
    artifact_id: str
    format: str
    display_name: str
    media_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["ok", "error"] = "ok"
    error: str = ""


class ImplementedChangeSummary(StrictModel):
    critique_id: str
    target_path: str = ""
    summary: str


class ReviewSummary(StrictModel):
    policy: str = "legacy_unknown"
    reviewed_roles: list[str] = Field(default_factory=list)
    validator_completed: bool = False
    independent_review_complete: bool = False
    content_changed: bool = False


class EngineResult(StrictModel):
    engine_run_id: str
    external_job_id: str
    pipeline_status: str
    stop_reason: str | None = None
    best_version_id: str
    last_version_id: str
    best_lesson_plan: LessonPlanDocument
    rubric_scores: RubricScores | None = None
    overall_score: float | None = Field(default=None, ge=0, le=10)
    optimization: dict[str, JsonValue] | None = None
    review: ReviewSummary | None = None
    implemented_changes: list[ImplementedChangeSummary] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
    artifacts: list[EngineArtifact] = Field(default_factory=list)


class RawParagraph(StrictModel):
    locator: str
    style: str = ""
    text: str


class RawTableCell(StrictModel):
    locator: str
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    text: str


class RawTable(StrictModel):
    locator: str
    rows: int = Field(ge=0)
    columns: int = Field(ge=0)
    cells: list[RawTableCell] = Field(default_factory=list)


class RawBlock(StrictModel):
    """One paragraph or table row in the order it appears in the Word body."""

    locator: str
    kind: Literal["paragraph", "table_row"]
    text: str
    style: str = ""


class RawLessonDocument(StrictModel):
    schema_version: Literal["paper4-raw-docx-v0.1"] = "paper4-raw-docx-v0.1"
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    original_filename: str
    paragraphs: list[RawParagraph] = Field(default_factory=list)
    tables: list[RawTable] = Field(default_factory=list)
    ordered_blocks: list[RawBlock] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def character_count(self) -> int:
        return sum(len(item.text) for item in self.paragraphs) + sum(
            len(cell.text) for table in self.tables for cell in table.cells
        )


class NormalizedLessonInput(StrictModel):
    schema_version: Literal["paper4-normalized-docx-v0.1"] = (
        "paper4-normalized-docx-v0.1"
    )
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    parser_version: str = "safe-docx-v0.1"
    normalizer_prompt_version: str = "1.0"
    metadata_provenance: dict[str, Literal["user", "file", "inferred"]]
    lesson_plan: LessonPlanDocument
    preserved_content_map: dict[str, list[str]] = Field(default_factory=dict)
    raw_locator_coverage: dict[str, list[str]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    estimated_cost: float = Field(default=0, ge=0)
    model_metadata: dict[str, JsonValue] = Field(default_factory=dict)


class NormalizationModelOutput(StrictModel):
    metadata_provenance: dict[str, Literal["user", "file", "inferred"]]
    lesson_plan: LessonPlanDocument
    preserved_content_map: dict[str, list[str]] = Field(default_factory=dict)
    raw_locator_coverage: dict[str, list[str]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
