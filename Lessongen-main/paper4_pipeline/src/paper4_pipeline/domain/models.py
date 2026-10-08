"""Versioned, strict contracts for the Paper#4 pipeline.

The domain layer deliberately has no LangGraph or model-provider dependency.
It is the shared contract for agents, deterministic control code, adapters,
experiments, and exporters.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    """Reject accidental fields so experiments cannot silently drift."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class TaskMode(str, Enum):
    GENERATE = "generate"
    OPTIMIZE = "optimize"


class Language(str, Enum):
    ZH = "zh"
    EN = "en"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CritiqueSource(str, Enum):
    CRITIC = "critic"
    SIMULATION = "simulation"
    HUMAN = "human"
    FUNCTION1 = "function1"


class CritiqueStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MERGED = "merged"
    DEFERRED = "deferred"
    IMPLEMENTED = "implemented"
    PARTIALLY_IMPLEMENTED = "partially_implemented"
    UNRESOLVED = "unresolved"
    VERIFIED_FIXED = "verified_fixed"
    REOPENED = "reopened"
    REGRESSION = "regression"


class ValidationDecisionKind(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    MERGE = "merge"
    DEFER = "defer"


class JudgeRecommendation(str, Enum):
    CONTINUE = "continue"
    STOP = "stop"
    ROLLBACK = "rollback"
    HUMAN_REVIEW = "human_review"


class RouteAction(str, Enum):
    CONTINUE_REVIEW = "continue_review"
    REWRITE = "rewrite"
    ROLLBACK = "rollback"
    FINALIZE = "finalize"
    HUMAN_REVIEW = "human_review"
    FAIL = "fail"


class StopReason(str, Enum):
    QUALITY_PASSED = "quality_passed"
    NO_ACTIONABLE_FEEDBACK = "no_actionable_feedback"
    PLATEAU = "plateau"
    OSCILLATION = "oscillation"
    REGRESSION_GUARD = "regression_guard"
    REWRITE_FAILED = "rewrite_failed"
    MAX_ROUNDS = "max_rounds"
    BUDGET_EXCEEDED = "budget_exceeded"
    HUMAN_STOP = "human_stop"
    VALIDATION_ERROR = "validation_error"
    RUNTIME_ERROR = "runtime_error"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_HUMAN = "needs_human"


class RubricDimension(str, Enum):
    CURRICULUM_ALIGNMENT = "curriculum_alignment"
    KNOWLEDGE_ACCURACY = "knowledge_accuracy"
    TEACHING_LOGIC = "teaching_logic"
    CLASSROOM_FEASIBILITY = "classroom_feasibility"
    DIFFERENTIATED_INSTRUCTION = "differentiated_instruction"
    STUDENT_ENGAGEMENT = "student_engagement"
    ASSESSMENT_DESIGN = "assessment_design"
    LANGUAGE_AND_FORMAT = "language_and_format"


class LearningObjective(StrictModel):
    objective_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence_of_achievement: str = ""
    standard_refs: list[str] = Field(default_factory=list)


class LessonQuestion(StrictModel):
    question: str = Field(min_length=1)
    expected_responses: list[str] = Field(default_factory=list)
    possible_misconceptions: list[str] = Field(default_factory=list)
    teacher_follow_ups: list[str] = Field(default_factory=list)
    evidence_to_notice: str = ""


class TeachingResource(StrictModel):
    resource_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    ready_to_use_content: str = ""


class TeacherResponseBranch(StrictModel):
    trigger: str = Field(min_length=1)
    teacher_move: str = Field(min_length=1)
    purpose: str = ""


class TeachingArtifact(StrictModel):
    artifact_id: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    purpose: str = ""
    content: str = Field(min_length=1)
    answer_or_success_criteria: str = ""


class ProcedureStep(StrictModel):
    step_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    duration_minutes: int = Field(ge=1, le=240)
    objective_ids: list[str] = Field(default_factory=list)
    teacher_actions: list[str] = Field(default_factory=list)
    student_actions: list[str] = Field(default_factory=list)
    questions: list[LessonQuestion] = Field(default_factory=list)
    assessment: str = ""
    design_rationale: str = ""
    resource_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    transition: str = ""
    student_product: str = ""
    success_criteria: list[str] = Field(default_factory=list)
    scaffolds: list[str] = Field(default_factory=list)
    extensions: list[str] = Field(default_factory=list)
    response_branches: list[TeacherResponseBranch] = Field(default_factory=list)


class LessonMetadata(StrictModel):
    subject: str = Field(min_length=1)
    grade: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    duration_minutes: int = Field(ge=5, le=240)
    textbook_version: str = ""


class DesignCandidate(StrictModel):
    candidate_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    design_thesis: str = Field(min_length=1)
    driving_question: str = Field(min_length=1)
    learner_starting_point: str = Field(min_length=1)
    desired_conceptual_shift: str = Field(min_length=1)
    learning_arc: list[str] = Field(min_length=3, max_length=7)
    pivotal_moment: str = Field(min_length=1)
    student_products: list[str] = Field(min_length=1)
    concrete_materials: list[str] = Field(min_length=1)
    subject_specific_value: str = Field(min_length=1)
    risks: list[str] = Field(default_factory=list)


class LessonDesignBlueprint(StrictModel):
    schema_version: Literal["paper4-design-blueprint-v0.1"] = (
        "paper4-design-blueprint-v0.1"
    )
    blueprint_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    candidates: list[DesignCandidate] = Field(min_length=2, max_length=3)
    selected_candidate_id: str = Field(min_length=1)
    selection_reason: str = Field(min_length=1)
    quality_non_negotiables: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_candidate_selection(self) -> "LessonDesignBlueprint":
        identifiers = [item.candidate_id for item in self.candidates]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate design candidate IDs are not allowed")
        if self.selected_candidate_id not in set(identifiers):
            raise ValueError("selected_candidate_id must reference a candidate")
        return self


class LessonPlanDocument(StrictModel):
    """Canonical lesson-plan content independent of Markdown/Word layout."""

    schema_version: Literal["paper4-lesson-plan-v0.1"] = "paper4-lesson-plan-v0.1"
    plan_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    template_id: str = "general_v0_1"
    metadata: LessonMetadata
    design_thesis: str = ""
    driving_question: str = ""
    learning_trajectory: list[str] = Field(default_factory=list)
    curriculum_standards: list[str] = Field(default_factory=list)
    content_analysis: str = ""
    student_analysis: str = ""
    learning_objectives: list[LearningObjective] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    difficult_points: list[str] = Field(default_factory=list)
    teaching_strategy: str = ""
    resources: list[TeachingResource] = Field(default_factory=list)
    teaching_artifacts: list[TeachingArtifact] = Field(default_factory=list)
    procedure_steps: list[ProcedureStep] = Field(default_factory=list)
    assessment_plan: str = ""
    differentiation: str = ""
    homework: str = ""
    board_design: str = ""
    reflection: str = ""
    references: list[str] = Field(default_factory=list)
    template_extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_identifiers_and_references(self) -> "LessonPlanDocument":
        objective_ids = [item.objective_id for item in self.learning_objectives]
        step_ids = [item.step_id for item in self.procedure_steps]
        resource_ids = [item.resource_id for item in self.resources]
        artifact_ids = [item.artifact_id for item in self.teaching_artifacts]
        for label, values in (
            ("objective_id", objective_ids),
            ("step_id", step_ids),
            ("resource_id", resource_ids),
            ("artifact_id", artifact_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} values are not allowed")

        known_objectives = set(objective_ids)
        known_resources = set(resource_ids)
        known_artifacts = set(artifact_ids)
        for step in self.procedure_steps:
            unknown_objectives = set(step.objective_ids) - known_objectives
            if unknown_objectives:
                raise ValueError(
                    f"{step.step_id} references unknown objectives: "
                    f"{sorted(unknown_objectives)}"
                )
            unknown_resources = set(step.resource_ids) - known_resources
            if unknown_resources:
                raise ValueError(
                    f"{step.step_id} references unknown resources: "
                    f"{sorted(unknown_resources)}"
                )
            unknown_artifacts = set(step.artifact_ids) - known_artifacts
            if unknown_artifacts:
                raise ValueError(
                    f"{step.step_id} references unknown teaching artifacts: "
                    f"{sorted(unknown_artifacts)}"
                )
        return self


class LessonTask(StrictModel):
    schema_version: Literal["paper4-task-v0.1"] = "paper4-task-v0.1"
    task_id: str = Field(min_length=1)
    mode: TaskMode = TaskMode.GENERATE
    language: Language = Language.ZH
    subject: str = Field(min_length=1)
    grade: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    duration_minutes: int = Field(default=45, ge=5, le=240)
    course_information: str = Field(min_length=1)
    textbook_content: str = ""
    curriculum_standards: list[str] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)
    student_profile: str = ""
    class_constraints: dict[str, JsonValue] = Field(default_factory=dict)
    available_resources: list[str] = Field(default_factory=list)
    required_sections: list[str] = Field(default_factory=list)
    rubric_id: str = "paper4-eight-dimension-v0.1"
    source_refs: list[str] = Field(default_factory=list)
    initial_plan: LessonPlanDocument | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator(
        "curriculum_standards",
        "learning_objectives",
        "available_resources",
        "required_sections",
        "source_refs",
    )
    @classmethod
    def remove_empty_items(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value and value.strip()]

    @model_validator(mode="after")
    def validate_mode(self) -> "LessonTask":
        if self.mode == TaskMode.OPTIMIZE and self.initial_plan is None:
            raise ValueError("optimize mode requires initial_plan")
        if self.mode == TaskMode.GENERATE and self.initial_plan is not None:
            raise ValueError("generate mode must not include initial_plan")
        if self.initial_plan and self.initial_plan.task_id != self.task_id:
            raise ValueError("initial_plan.task_id must match task_id")
        if self.initial_plan:
            metadata = self.initial_plan.metadata
            if (
                metadata.subject != self.subject
                or metadata.grade != self.grade
                or metadata.topic != self.topic
            ):
                raise ValueError(
                    "initial_plan subject, grade, and topic must match the task"
                )
        return self


class KnowledgeFragment(StrictModel):
    fragment_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_version: str = "unknown"
    location: str = ""
    content: str = Field(min_length=1)
    content_hash: str = Field(min_length=8)


class KnowledgeBundle(StrictModel):
    schema_version: Literal["paper4-knowledge-v0.1"] = "paper4-knowledge-v0.1"
    bundle_id: str = Field(min_length=1)
    bundle_version: str = "0.1"
    owner_profile_id: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    retrieved_fragments: list[KnowledgeFragment] = Field(default_factory=list)
    retrieval_query: str = ""
    retrieval_parameters: dict[str, JsonValue] = Field(default_factory=dict)
    status: Literal["ok", "empty", "partial", "error"] = "empty"

    @model_validator(mode="after")
    def validate_status(self) -> "KnowledgeBundle":
        if self.status == "empty" and self.retrieved_fragments:
            raise ValueError("empty knowledge bundle cannot contain fragments")
        if self.status == "ok" and not self.retrieved_fragments:
            raise ValueError("ok knowledge bundle requires at least one fragment")
        fragment_sources = {item.source_id for item in self.retrieved_fragments}
        if not fragment_sources <= set(self.source_ids):
            raise ValueError("retrieved fragment source must be declared in source_ids")
        return self


class ModelConfig(StrictModel):
    provider: Literal["deepseek_openai_compatible"] = "deepseek_openai_compatible"
    model_name: Literal["deepseek-v4-flash"] = "deepseek-v4-flash"
    base_url_env: str = "DEEPSEEK_BASE_URL"
    base_url_default: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=512, le=32768)
    timeout_seconds: float = Field(default=180.0, gt=0, le=600)
    max_retries: int = Field(default=2, ge=0, le=5)
    thinking_mode: Literal["enabled", "disabled"] = "disabled"
    reasoning_effort: Literal["low", "high", "max"] = "low"
    input_cost_per_million: float = Field(default=0.44, ge=0)
    output_cost_per_million: float = Field(default=1.32, ge=0)


class AgentProfile(StrictModel):
    schema_version: Literal["paper4-agent-profile-v0.1"] = (
        "paper4-agent-profile-v0.1"
    )
    profile_id: str = Field(min_length=1)
    profile_version: str = "0.1"
    role: str = Field(min_length=1)
    expertise_scope: list[str] = Field(default_factory=list)
    knowledge_source_ids: list[str] = Field(default_factory=list)
    rubric_dimensions: list[RubricDimension] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    visible_state_fields: list[str] = Field(default_factory=list)
    prompt_id: str = Field(min_length=1)
    prompt_version: str = "0.1"
    model: ModelConfig = Field(default_factory=ModelConfig)


class RuleViolation(StrictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    location: str = ""
    severity: Severity = Severity.MEDIUM


class RuleCheckReport(StrictModel):
    schema_version: Literal["paper4-rule-report-v0.1"] = (
        "paper4-rule-report-v0.1"
    )
    report_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    passed: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    violations: list[RuleViolation] = Field(default_factory=list)
    total_duration_minutes: int = Field(ge=0)
    expected_duration_minutes: int = Field(ge=0)


class CritiqueTransition(StrictModel):
    from_status: CritiqueStatus | None = None
    to_status: CritiqueStatus
    round_index: int = Field(ge=0)
    version_id: str = ""
    note: str = ""


class CritiqueItem(StrictModel):
    schema_version: Literal["paper4-critique-v0.1"] = "paper4-critique-v0.1"
    critique_id: str = Field(min_length=1)
    source: CritiqueSource = CritiqueSource.CRITIC
    critic_profile_id: str | None = None
    dimension: RubricDimension
    issue_code: str = Field(min_length=1)
    target_path: str = Field(
        pattern=r"^/(design_thesis|driving_question|learning_trajectory|curriculum_standards|content_analysis|student_analysis|learning_objectives|key_points|difficult_points|teaching_strategy|resources|teaching_artifacts|procedure_steps|assessment_plan|differentiation|homework|board_design|reflection|references)(/.*)?$"
    )
    lesson_location: str = Field(min_length=1)
    lesson_section_id: str = ""
    procedure_step_id: str = ""
    issue: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    knowledge_source_refs: list[str] = Field(default_factory=list)
    severity: Severity = Severity.MEDIUM
    actionable_suggestion: str = Field(min_length=1)
    confidence: float = Field(default=0.8, ge=0, le=1)
    status: CritiqueStatus = CritiqueStatus.PROPOSED
    canonical_critique_id: str = ""
    introduced_in_round: int = Field(default=0, ge=0)
    validated_in_round: int | None = Field(default=None, ge=0)
    implemented_in_version_id: str = ""
    verified_in_round: int | None = Field(default=None, ge=0)
    history: list[CritiqueTransition] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_profile(self) -> "CritiqueItem":
        if self.source == CritiqueSource.CRITIC and not self.critic_profile_id:
            raise ValueError("critic source requires critic_profile_id")
        if not self.history:
            if self.status != CritiqueStatus.PROPOSED:
                raise ValueError("critique without history must be proposed")
            return self
        if self.history[0].from_status != CritiqueStatus.PROPOSED:
            raise ValueError("critique history must start from proposed")
        previous = self.history[0].from_status
        previous_round = -1
        for transition in self.history:
            if transition.from_status != previous:
                raise ValueError("critique history contains a discontinuity")
            if transition.round_index < previous_round:
                raise ValueError("critique history round indices must be monotonic")
            previous = transition.to_status
            previous_round = transition.round_index
        if previous != self.status:
            raise ValueError("critique status must match the last history event")
        return self


class CritiqueBatch(StrictModel):
    schema_version: Literal["paper4-critique-batch-v0.1"] = (
        "paper4-critique-batch-v0.1"
    )
    batch_id: str = Field(min_length=1)
    plan_version_id: str = Field(min_length=1)
    round_index: int = Field(ge=0)
    items: list[CritiqueItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "CritiqueBatch":
        values = [item.critique_id for item in self.items]
        if len(values) != len(set(values)):
            raise ValueError("duplicate critique_id values are not allowed")
        return self


class ValidationDecision(StrictModel):
    schema_version: Literal["paper4-validation-v0.1"] = "paper4-validation-v0.1"
    decision_id: str = Field(min_length=1)
    critique_id: str = Field(min_length=1)
    decision: ValidationDecisionKind
    grounded: bool
    relevant: bool
    actionable: bool
    conflict: bool = False
    priority: int = Field(default=0, ge=0, le=100)
    reason: str = Field(min_length=1)
    canonical_critique_id: str = ""

    @model_validator(mode="after")
    def validate_merge_target(self) -> "ValidationDecision":
        if (
            self.decision == ValidationDecisionKind.MERGE
            and not self.canonical_critique_id
        ):
            raise ValueError("merge decision requires canonical_critique_id")
        if self.decision == ValidationDecisionKind.MERGE:
            if self.canonical_critique_id == self.critique_id:
                raise ValueError("merge decision cannot target itself")
        elif self.canonical_critique_id:
            raise ValueError("canonical_critique_id is only valid for merge")
        if self.decision == ValidationDecisionKind.ACCEPT and not (
            self.grounded and self.relevant and self.actionable and not self.conflict
        ):
            raise ValueError(
                "accepted critique must be grounded, relevant, actionable, and conflict-free"
            )
        return self


class ValidationBatch(StrictModel):
    schema_version: Literal["paper4-validation-batch-v0.1"] = (
        "paper4-validation-batch-v0.1"
    )
    batch_id: str = Field(min_length=1)
    critique_batch_id: str = Field(min_length=1)
    round_index: int = Field(ge=0)
    decisions: list[ValidationDecision] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_decisions(self) -> "ValidationBatch":
        decision_ids = [item.decision_id for item in self.decisions]
        critique_ids = [item.critique_id for item in self.decisions]
        if len(decision_ids) != len(set(decision_ids)):
            raise ValueError("duplicate decision_id values are not allowed")
        if len(critique_ids) != len(set(critique_ids)):
            raise ValueError("each critique may receive only one decision")
        return self


class RubricScores(StrictModel):
    curriculum_alignment: float = Field(ge=0, le=10)
    knowledge_accuracy: float = Field(ge=0, le=10)
    teaching_logic: float = Field(ge=0, le=10)
    classroom_feasibility: float = Field(ge=0, le=10)
    differentiated_instruction: float = Field(ge=0, le=10)
    student_engagement: float = Field(ge=0, le=10)
    assessment_design: float = Field(ge=0, le=10)
    language_and_format: float = Field(ge=0, le=10)

    def values_list(self) -> list[float]:
        return [float(value) for value in self.model_dump().values()]


class DesignQualitySignals(StrictModel):
    genericity_risk: float = Field(ge=0, le=10)
    disciplinary_depth: float = Field(ge=0, le=10)
    design_coherence: float = Field(ge=0, le=10)
    material_readiness: float = Field(ge=0, le=10)


class EvaluationReport(StrictModel):
    schema_version: Literal["paper4-evaluation-v0.1"] = (
        "paper4-evaluation-v0.1"
    )
    evaluation_id: str = Field(min_length=1)
    evaluated_version_id: str = Field(min_length=1)
    rubric_id: str = "paper4-eight-dimension-v0.1"
    rubric_scores: RubricScores
    quality_signals: DesignQualitySignals | None = None
    overall_score: float = Field(ge=0, le=10)
    high_risk_issue_ids: list[str] = Field(default_factory=list)
    unresolved_issue_count: int = Field(default=0, ge=0)
    rule_checks_passed: bool
    recommended_action: JudgeRecommendation = JudgeRecommendation.CONTINUE
    compared_version_ids: list[str] = Field(default_factory=list)
    regressions: list[str] = Field(default_factory=list)
    summary: str = ""

    @model_validator(mode="after")
    def validate_score_aggregation(self) -> "EvaluationReport":
        expected = sum(self.rubric_scores.values_list()) / 8
        if abs(self.overall_score - expected) > 0.011:
            raise ValueError(
                "overall_score must equal the arithmetic mean of the eight rubric scores"
            )
        return self


class RewriteChange(StrictModel):
    critique_id: str = Field(min_length=1)
    target_path: str = Field(min_length=1)
    # target_path locates the *problem*. A valid solution may edit a different
    # field in the same lesson design (e.g. simplify a task instead of changing
    # its duration). Keep old records readable while new live runs require it.
    edited_paths: list[str] = Field(default_factory=list)
    lesson_location: str = Field(min_length=1)
    before_summary: str
    after_summary: str
    implementation_status: Literal["implemented", "partially_implemented"]


class RewriteOutcome(StrictModel):
    schema_version: Literal["paper4-rewrite-outcome-v0.1"] = (
        "paper4-rewrite-outcome-v0.1"
    )
    document: LessonPlanDocument
    changes: list[RewriteChange] = Field(default_factory=list)
    unresolved_critique_ids: list[str] = Field(default_factory=list)
    unresolved_reasons: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_change_sets(self) -> "RewriteOutcome":
        change_ids = [item.critique_id for item in self.changes]
        if len(change_ids) != len(set(change_ids)):
            raise ValueError("rewrite outcome has duplicate critique mappings")
        if len(self.unresolved_critique_ids) != len(set(self.unresolved_critique_ids)):
            raise ValueError("rewrite outcome has duplicate unresolved critique IDs")
        if set(change_ids) & set(self.unresolved_critique_ids):
            raise ValueError("critique cannot be both changed and unresolved")
        if set(self.unresolved_reasons) - set(self.unresolved_critique_ids):
            raise ValueError("unresolved reason refers to a changed or unknown critique")
        return self


class RewriteRecord(StrictModel):
    schema_version: Literal["paper4-rewrite-record-v0.1"] = (
        "paper4-rewrite-record-v0.1"
    )
    rewrite_id: str = Field(min_length=1)
    input_version_id: str = Field(min_length=1)
    output_version_id: str = Field(min_length=1)
    strategy: Literal["targeted_patch", "full_document", "legacy_unknown"] = "legacy_unknown"
    accepted_critique_ids: list[str] = Field(default_factory=list)
    changes: list[RewriteChange] = Field(default_factory=list)
    unresolved_critique_ids: list[str] = Field(default_factory=list)
    unresolved_reasons: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_conservation(self) -> "RewriteRecord":
        changed_ids = [item.critique_id for item in self.changes]
        if len(changed_ids) != len(set(changed_ids)):
            raise ValueError("rewrite record has duplicate change mappings")
        if len(self.unresolved_critique_ids) != len(set(self.unresolved_critique_ids)):
            raise ValueError("rewrite record has duplicate unresolved critique IDs")
        if len(self.accepted_critique_ids) != len(set(self.accepted_critique_ids)):
            raise ValueError("rewrite record has duplicate accepted critique IDs")
        changed = set(changed_ids)
        unresolved = set(self.unresolved_critique_ids)
        accepted = set(self.accepted_critique_ids)
        if set(self.unresolved_reasons) - unresolved:
            raise ValueError("rewrite record has an unknown unresolved reason")
        if changed & unresolved:
            raise ValueError("critique cannot be both changed and unresolved")
        if accepted != changed | unresolved:
            raise ValueError(
                "every accepted critique must be changed or explicitly unresolved"
            )
        if self.input_version_id == self.output_version_id:
            raise ValueError("rewrite output must be a new version")
        return self


class TokenUsage(StrictModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ModelCallAttempt(StrictModel):
    schema_version: Literal["paper4-model-call-v0.1"] = "paper4-model-call-v0.1"
    call_id: str = ""  # empty only when reading an older P1 ledger
    attempt_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    prompt_id: str = Field(min_length=1)
    prompt_sha256: str = Field(min_length=64, max_length=64)
    config_sha256: str = Field(min_length=64, max_length=64)
    rate_id: str = Field(min_length=1)
    attempt_index: int = Field(ge=1)
    status: Literal["ok", "invalid_output", "truncated", "failed", "cancelled"]
    usage_source: Literal["provider_response", "truncation_exception", "unknown"] = "unknown"
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost: float | None = Field(default=None, ge=0)
    duration_seconds: float = Field(ge=0)
    finish_reason: str = ""
    error_type: str = ""


class LessonPlanVersion(StrictModel):
    schema_version: Literal["paper4-plan-version-v0.1"] = (
        "paper4-plan-version-v0.1"
    )
    version_id: str = Field(min_length=1)
    parent_version_id: str = ""
    branch_id: str = "main"
    strategy_id: str = "general"
    iteration: int = Field(ge=0)
    document: LessonPlanDocument
    created_by_profile_id: str = Field(min_length=1)
    created_at: datetime
    document_hash: str = Field(min_length=64, max_length=64)
    addressed_critique_ids: list[str] = Field(default_factory=list)
    unresolved_critique_ids: list[str] = Field(default_factory=list)
    diff_summary: str = ""
    rule_check_report: RuleCheckReport
    internal_evaluation: EvaluationReport | None = None
    change_count: int = Field(default=0, ge=0)
    estimated_cost: float = Field(default=0, ge=0)

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class IterationRecord(StrictModel):
    schema_version: Literal["paper4-iteration-v0.1"] = "paper4-iteration-v0.1"
    iteration_id: str = Field(min_length=1)
    round_index: int = Field(ge=0)
    input_version_id: str = Field(min_length=1)
    output_version_id: str = ""
    critique_ids: list[str] = Field(default_factory=list)
    validation_decision_ids: list[str] = Field(default_factory=list)
    evaluation_id: str = ""
    rewrite_id: str = ""
    regressions: list[str] = Field(default_factory=list)
    score_delta: float = 0
    duration_seconds: float = Field(default=0, ge=0)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    estimated_cost: float = Field(default=0, ge=0)
    route: RouteAction
    route_decision_id: str = ""


class BudgetConfig(StrictModel):
    max_model_calls: int = Field(default=30, ge=1)
    max_total_tokens: int = Field(default=80000, ge=1)
    max_estimated_cost: float = Field(default=10.0, ge=0)
    max_runtime_seconds: float = Field(default=600.0, gt=0)


class ExperimentConfig(StrictModel):
    schema_version: Literal["paper4-experiment-v0.1"] = (
        "paper4-experiment-v0.1"
    )
    experiment_id: str = Field(min_length=1)
    method_id: str = Field(min_length=1)
    execution_mode: Literal["live"] = "live"
    random_seed: int = 20260830
    designer_profile_id: str = "design_architect_v0_1"
    writer_profile_id: str = "writer_v0_1"
    critic_profile_ids: list[str] = Field(
        default_factory=lambda: [
            "subject_critic_v0_1",
            "pedagogy_critic_v0_1",
            "alignment_critic_v0_1",
        ]
    )
    validator_profile_id: str = "validator_v0_1"
    judge_profile_id: str = "judge_v0_1"
    rewriter_profile_id: str = "rewriter_v0_1"
    role_model_configs: dict[str, ModelConfig] = Field(default_factory=dict)
    knowledge_policy: Literal["homogeneous", "heterogeneous"] = "heterogeneous"
    interaction_protocol: Literal[
        "independent_review",
        "sequential_review",
        "debate",
        "cross_examination",
        "proposer_challenger",
    ] = "independent_review"
    # Existing serialized run results remain readable. New tasks require a
    # review by default; the historical fast path is an explicit experiment.
    generation_review_policy: Literal[
        "at_least_one_independent_review", "judge_first_fast_path"
    ] = "at_least_one_independent_review"
    max_rounds: int = Field(default=3, ge=0, le=20)
    # Optimization is a bounded revision task, not a second generation run.
    optimization_max_rounds: int = Field(default=3, ge=1, le=20)
    patience: int = Field(default=2, ge=1, le=10)
    epsilon: float = Field(default=0.1, ge=0, le=10)
    quality_threshold: float = Field(default=8.0, ge=0, le=10)
    optimization_quality_threshold: float = Field(default=8.0, ge=0, le=10)
    optimization_min_score_gain: float = Field(default=0.2, ge=0, le=10)
    optimization_dimension_drop_tolerance: float = Field(default=0.3, ge=0, le=10)
    critical_dimension_floor: float = Field(default=7.0, ge=0, le=10)
    duration_tolerance_minutes: int = Field(default=2, ge=0, le=30)
    max_model_calls: int = Field(default=30, ge=1)
    max_total_tokens: int = Field(default=80000, ge=1)
    optimization_max_model_calls: int | None = Field(default=None, ge=1)
    optimization_max_total_tokens: int | None = Field(default=None, ge=1)
    max_estimated_cost: float = Field(default=10.0, ge=0)
    max_runtime_seconds: float = Field(default=600.0, gt=0)
    enable_paper3: bool = False
    enable_docx: bool = False

    @model_validator(mode="after")
    def validate_live_model_profiles(self) -> "ExperimentConfig":
        required = {
            self.designer_profile_id,
            self.writer_profile_id,
            *self.critic_profile_ids,
            self.validator_profile_id,
            self.judge_profile_id,
            self.rewriter_profile_id,
        }
        missing = required - set(self.role_model_configs)
        if missing:
            raise ValueError(f"missing role_model_configs for: {sorted(missing)}")
        if any(
            item.model_name != "deepseek-v4-flash"
            for item in self.role_model_configs.values()
        ):
            raise ValueError("all v0.1 agents must use deepseek-v4-flash")
        return self

    @property
    def budgets(self) -> BudgetConfig:
        return BudgetConfig(
            max_model_calls=self.max_model_calls,
            max_total_tokens=self.max_total_tokens,
            max_estimated_cost=self.max_estimated_cost,
            max_runtime_seconds=self.max_runtime_seconds,
        )


class RouteDecision(StrictModel):
    schema_version: Literal["paper4-route-v0.1"] = "paper4-route-v0.1"
    decision_id: str = Field(min_length=1)
    next_action: RouteAction
    primary_reason: StopReason | None = None
    triggered_reasons: list[StopReason] = Field(default_factory=list)
    explanation: str = ""


class VersionSelection(StrictModel):
    schema_version: Literal["paper4-version-selection-v0.1"] = (
        "paper4-version-selection-v0.1"
    )
    selection_id: str = Field(min_length=1)
    selected_version_id: str = Field(min_length=1)
    eligible_candidate_ids: list[str] = Field(default_factory=list)
    eliminated_candidates: dict[str, list[str]] = Field(default_factory=dict)
    ambiguous_candidate_ids: list[str] = Field(default_factory=list)
    requires_human: bool = False
    selection_policy_version: str = "best-version-v0.1"
    selection_reason: str = ""

    @model_validator(mode="after")
    def validate_selection_sets(self) -> "VersionSelection":
        eligible = set(self.eligible_candidate_ids)
        eliminated = set(self.eliminated_candidates)
        if eligible & eliminated:
            raise ValueError("eligible and eliminated candidates must be disjoint")
        if eligible and self.selected_version_id not in eligible:
            raise ValueError("selected version must be eligible")
        if not set(self.ambiguous_candidate_ids) <= eligible:
            raise ValueError("ambiguous candidates must be eligible")
        return self


class ArtifactRecord(StrictModel):
    artifact_id: str = Field(min_length=1)
    format: Literal["json", "markdown", "docx", "trace"]
    path: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    status: Literal["ok", "error"] = "ok"
    error: str = ""


class ArtifactManifest(StrictModel):
    schema_version: Literal["paper4-artifact-manifest-v0.1"] = (
        "paper4-artifact-manifest-v0.1"
    )
    manifest_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    best_version_id: str = Field(min_length=1)
    last_version_id: str = Field(min_length=1)
    lesson_plan_schema_version: str
    template_id: str
    template_version: str
    artifacts: list[ArtifactRecord] = Field(default_factory=list)


class PipelineResult(StrictModel):
    schema_version: Literal["paper4-run-result-v0.1"] = "paper4-run-result-v0.1"
    run_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    task_mode: TaskMode | None = None
    experiment_id: str = Field(min_length=1)
    method_id: str = Field(min_length=1)
    status: RunStatus
    stop_reason: StopReason | None = None
    best_version_id: str = ""
    last_version_id: str = ""
    design_blueprint: LessonDesignBlueprint | None = None
    versions: list[LessonPlanVersion] = Field(default_factory=list)
    critiques: list[CritiqueItem] = Field(default_factory=list)
    validation_batches: list[ValidationBatch] = Field(default_factory=list)
    rewrite_records: list[RewriteRecord] = Field(default_factory=list)
    route_decisions: list[RouteDecision] = Field(default_factory=list)
    version_selections: list[VersionSelection] = Field(default_factory=list)
    iterations: list[IterationRecord] = Field(default_factory=list)
    optimization_quality_gate: dict[str, JsonValue] | None = None
    optimization_comparison: dict[str, JsonValue] | None = None
    model_call_count: int = Field(default=0, ge=0)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    estimated_cost: float = Field(default=0, ge=0)
    model_calls: list[ModelCallAttempt] = Field(default_factory=list)
    trace_path: str = ""
    artifacts: ArtifactManifest | None = None
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_version_references(self) -> "PipelineResult":
        if self.status == RunStatus.COMPLETED and self.stop_reason is None:
            raise ValueError("completed result requires stop_reason")
        if self.status == RunStatus.FAILED and self.stop_reason not in {
            StopReason.RUNTIME_ERROR,
            StopReason.VALIDATION_ERROR,
            StopReason.REWRITE_FAILED,
            StopReason.REGRESSION_GUARD,
        }:
            raise ValueError("failed result requires a failure stop_reason")
        if not self.versions:
            if self.best_version_id or self.last_version_id:
                raise ValueError("empty run cannot reference a version")
            return self
        version_ids_list = [version.version_id for version in self.versions]
        if len(version_ids_list) != len(set(version_ids_list)):
            raise ValueError("duplicate version_id values are not allowed")
        version_ids = set(version_ids_list)
        if self.best_version_id not in version_ids:
            raise ValueError("best_version_id must reference a saved version")
        if self.last_version_id not in version_ids:
            raise ValueError("last_version_id must reference a saved version")
        for version in self.versions:
            if version.parent_version_id and version.parent_version_id not in version_ids:
                raise ValueError("version parent must reference a saved version")
            if version.document.task_id != self.task_id:
                raise ValueError("all versions must belong to the result task")
            if version.rule_check_report.plan_id != version.document.plan_id:
                raise ValueError("rule report must reference its version document")
            if (
                version.internal_evaluation
                and version.internal_evaluation.evaluated_version_id
                != version.version_id
            ):
                raise ValueError("evaluation must reference its version")
        selection_ids = {
            item.selection_id for item in self.version_selections
        }
        if len(selection_ids) != len(self.version_selections):
            raise ValueError("duplicate version selection IDs are not allowed")
        return self


class SimulationEvent(StrictModel):
    event_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    minute_start: int = Field(ge=0)
    minute_end: int = Field(ge=0)
    role: str = Field(min_length=1)
    observation: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_time_range(self) -> "SimulationEvent":
        if self.minute_end < self.minute_start:
            raise ValueError("minute_end must be greater than or equal to minute_start")
        return self


class SimulationIssue(StrictModel):
    issue_id: str = Field(min_length=1)
    type: Literal[
        "misconception", "timing", "engagement", "feasibility", "differentiation"
    ]
    severity: Severity
    lesson_section_id: str = ""
    procedure_step_id: str = ""
    evidence_event_ids: list[str] = Field(default_factory=list)
    description: str = Field(min_length=1)
    suggestion: str = Field(min_length=1)
    confidence: float = Field(default=0.8, ge=0, le=1)


class SimulationReport(StrictModel):
    schema_version: Literal["paper3-simulation-report-v0.1"] = (
        "paper3-simulation-report-v0.1"
    )
    simulation_id: str = Field(min_length=1)
    lesson_plan_version_id: str = Field(min_length=1)
    lesson_plan_hash: str = Field(min_length=8)
    events: list[SimulationEvent] = Field(default_factory=list)
    issues: list[SimulationIssue] = Field(default_factory=list)
    estimated_timing: dict[str, int] = Field(default_factory=dict)
    uncovered_objectives: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    model_and_prompt_version: dict[str, str] = Field(default_factory=dict)
