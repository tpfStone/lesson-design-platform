"""Real DeepSeek implementations of every model-backed Paper#4 role."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from pydantic import Field, model_validator

from paper4_pipeline.agents.profiles import default_profile_registry
from paper4_pipeline.agents.patch_rewriter import incremental_patch_rewrite
from paper4_pipeline.agents.optimization_compare import PairwiseComparison, compare
from paper4_pipeline.agents.prompts import load_prompt
from paper4_pipeline.agents.protocols import AgentOutput
from paper4_pipeline.agents.suite import AgentSuite
from paper4_pipeline.control.alignment import build_alignment_audit
from paper4_pipeline.control.evidence import build_task_evidence_profile
from paper4_pipeline.control.lifecycle import (
    DEFAULT_MAX_ACCEPTS_PER_ROUND,
    apply_validation,
    enforce_acceptance_cap,
    enforce_task_evidence_constraints,
)
from paper4_pipeline.control.rules import check_lesson_plan, lesson_target_changed
from paper4_pipeline.domain.ids import stable_id
from paper4_pipeline.domain.models import (
    AgentProfile,
    CritiqueBatch,
    CritiqueItem,
    CritiqueSource,
    CritiqueStatus,
    DesignQualitySignals,
    EvaluationReport,
    ExperimentConfig,
    JudgeRecommendation,
    KnowledgeBundle,
    LessonDesignBlueprint,
    LessonPlanDocument,
    LessonPlanVersion,
    LessonTask,
    RewriteOutcome,
    RubricDimension,
    RubricScores,
    Severity,
    StrictModel,
    ValidationBatch,
    ValidationDecision,
    ValidationDecisionKind,
)
from paper4_pipeline.providers.openai_compatible import OpenAICompatibleProvider


class CritiqueProposal(StrictModel):
    dimension: RubricDimension
    issue_code: str = Field(min_length=1, max_length=80)
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


class CritiqueProposalSet(StrictModel):
    items: list[CritiqueProposal] = Field(default_factory=list, max_length=8)
    review_summary: str = ""


class ValidationDecisionProposal(StrictModel):
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
    def validate_decision_shape(self) -> "ValidationDecisionProposal":
        if self.decision == ValidationDecisionKind.MERGE:
            if not self.canonical_critique_id:
                raise ValueError(
                    f"critique {self.critique_id!r}: merge requires "
                    "canonical_critique_id to name the accepted target"
                )
        elif self.canonical_critique_id:
            raise ValueError(
                f"critique {self.critique_id!r}: canonical_critique_id "
                f"{self.canonical_critique_id!r} is only allowed for merge"
            )
        if self.decision == ValidationDecisionKind.ACCEPT and not (
            self.grounded and self.relevant and self.actionable and not self.conflict
        ):
            raise ValueError(
                f"critique {self.critique_id!r}: accepted critique must pass "
                "all four validation gates"
            )
        return self


class ValidationProposalSet(StrictModel):
    decisions: list[ValidationDecisionProposal] = Field(default_factory=list)
    validation_summary: str = ""


class JudgeAssessment(StrictModel):
    rubric_scores: RubricScores
    quality_signals: DesignQualitySignals
    high_risk_issue_ids: list[str] = Field(default_factory=list)
    recommended_action: JudgeRecommendation = JudgeRecommendation.CONTINUE
    summary: str = Field(min_length=1)


class LiveDesignArchitect:
    def __init__(
        self,
        profile: AgentProfile,
        provider: OpenAICompatibleProvider,
        prompt_root: Path | None = None,
    ) -> None:
        self.profile = profile
        self.profile_id = profile.profile_id
        self.provider = provider
        self.prompt = load_prompt(profile.prompt_id, prompt_root)

    def design(
        self,
        task: LessonTask,
        knowledge: KnowledgeBundle | None = None,
    ) -> AgentOutput[LessonDesignBlueprint]:
        required_blueprint_id = stable_id("blueprint", task.task_id)

        def validate(value: LessonDesignBlueprint) -> None:
            if value.task_id != task.task_id:
                raise ValueError("designer changed required task_id")
            if value.blueprint_id != required_blueprint_id:
                raise ValueError("designer changed required blueprint_id")

        response = self.provider.invoke_structured(
            prompt=self.prompt,
            input_payload=_payload(
                task=task,
                profile=self.profile,
                knowledge=knowledge,
                required_identity={
                    "schema_version": "paper4-design-blueprint-v0.1",
                    "blueprint_id": required_blueprint_id,
                    "task_id": task.task_id,
                },
            ),
            output_schema=LessonDesignBlueprint,
            stage="design_architect",
            result_validator=validate,
        )
        return AgentOutput(
            value=response.value,
            usage=response.usage,
            estimated_cost=response.estimated_cost,
            metadata=response.metadata,
        )


def _payload(
    *,
    task: LessonTask,
    profile: AgentProfile,
    knowledge: KnowledgeBundle | None,
    **extra: object,
) -> dict[str, object]:
    result: dict[str, object] = {
        "task": task.model_dump(mode="json"),
        "agent_profile": profile.model_dump(mode="json"),
        "knowledge_bundle": knowledge.model_dump(mode="json") if knowledge else None,
    }
    result.update(extra)
    return result


class LiveWriter:
    def __init__(
        self,
        profile: AgentProfile,
        provider: OpenAICompatibleProvider,
        prompt_root: Path | None = None,
        *,
        duration_tolerance_minutes: int = 2,
    ) -> None:
        self.profile = profile
        self.profile_id = profile.profile_id
        self.provider = provider
        self.prompt = load_prompt(profile.prompt_id, prompt_root)
        # Kept in sync with the graph's rule-check tolerance so a config with a
        # wider duration tolerance is not stricter at the model-retry boundary.
        self.duration_tolerance_minutes = duration_tolerance_minutes

    def generate(
        self,
        task: LessonTask,
        knowledge: KnowledgeBundle | None = None,
        blueprint: LessonDesignBlueprint | None = None,
    ) -> AgentOutput[LessonPlanDocument]:
        required_plan_id = stable_id("plan", task.task_id, "v0")

        def validate(value: LessonPlanDocument) -> None:
            if value.task_id != task.task_id or value.plan_id != required_plan_id:
                raise ValueError("writer changed required task_id or plan_id")
            for field in ("subject", "grade", "topic", "duration_minutes"):
                if getattr(value.metadata, field) != getattr(task, field):
                    raise ValueError(f"writer changed immutable metadata.{field}")
            report = check_lesson_plan(
                value,
                task,
                duration_tolerance_minutes=self.duration_tolerance_minutes,
            )
            if not report.passed:
                errors = [item.message for item in report.violations]
                raise ValueError(f"writer output failed deterministic rules: {errors}")

        response = self.provider.invoke_structured(
            prompt=self.prompt,
            input_payload=_payload(
                task=task,
                profile=self.profile,
                knowledge=knowledge,
                design_blueprint=(
                    blueprint.model_dump(mode="json") if blueprint else None
                ),
                creative_brief={
                    "detail_level": task.metadata.get("detail_level", "showcase"),
                    "creative_intensity": task.metadata.get(
                        "creative_intensity", "high_but_grounded"
                    ),
                    "lesson_style": task.metadata.get(
                        "lesson_style", "choose_the_best_fit_for_this_topic"
                    ),
                    "desired_effect": (
                        "形成一条有辨识度的教学主线；情境、问题链、学生作品、"
                        "教师追问和评价证据具体到可以直接试教。"
                    ),
                    "avoid": [
                        "机械套用固定五段式",
                        "只写教师引导学生讨论等空泛动作",
                        "为了热闹加入与核心概念无关的活动",
                        "用华丽措辞代替教学设计",
                    ],
                },
                required_identity={
                    "schema_version": "paper4-lesson-plan-v0.1",
                    "plan_id": required_plan_id,
                    "task_id": task.task_id,
                    "template_id": "general_v0_1",
                },
            ),
            output_schema=LessonPlanDocument,
            stage="writer",
            result_validator=validate,
        )
        return AgentOutput(
            value=response.value,
            usage=response.usage,
            estimated_cost=response.estimated_cost,
            metadata=response.metadata,
        )


def _validate_critic_batch(
    proposals: CritiqueProposalSet,
    *,
    allowed_dimensions: set[RubricDimension],
    known_sources: set[str],
) -> None:
    """Enforce the structural boundary a critic must respect.

    A citation is legitimate when it names a declared source (a value from
    ``KnowledgeBundle.source_ids``) OR one of that source's retrieved fragments
    (a ``KnowledgeFragment.fragment_id``): the bundle JSON handed to the model
    shows both handles, so a model may reasonably cite either.  Fabricated ids
    still fail because they match neither set.
    """
    for item in proposals.items:
        if item.dimension not in allowed_dimensions:
            raise ValueError(
                f"critic used dimension outside role boundary: {item.dimension}"
            )
        unknown = set(item.knowledge_source_refs) - known_sources
        if unknown:
            raise ValueError(f"critic cited unknown knowledge sources: {unknown}")


class LiveCritic:
    def __init__(
        self,
        profile: AgentProfile,
        provider: OpenAICompatibleProvider,
        prompt_root: Path | None = None,
    ) -> None:
        self.profile = profile
        self.profile_id = profile.profile_id
        self.provider = provider
        self.prompt = load_prompt(profile.prompt_id, prompt_root)

    def review(
        self,
        task: LessonTask,
        version: LessonPlanVersion,
        round_index: int,
        knowledge: KnowledgeBundle | None = None,
        prior_critiques: list[CritiqueItem] | None = None,
    ) -> AgentOutput[CritiqueBatch]:
        allowed_dimensions = set(self.profile.rubric_dimensions)
        known_sources = set(knowledge.source_ids if knowledge else [])
        if knowledge:
            known_sources |= {
                item.fragment_id for item in knowledge.retrieved_fragments
            }

        def validate(proposals: CritiqueProposalSet) -> None:
            _validate_critic_batch(
                proposals,
                allowed_dimensions=allowed_dimensions,
                known_sources=known_sources,
            )

        response = self.provider.invoke_structured(
            prompt=self.prompt,
            input_payload=_payload(
                task=task,
                profile=self.profile,
                knowledge=knowledge,
                current_version=version.model_dump(mode="json"),
                round_index=round_index,
                prior_critiques=[
                    item.model_dump(mode="json") for item in (prior_critiques or [])
                ],
                alignment_audit=(
                    build_alignment_audit(version.document, task)
                    if self.profile.role == "alignment_critic"
                    else None
                ),
            ),
            output_schema=CritiqueProposalSet,
            stage=self.profile.role,
            result_validator=validate,
        )
        items: list[CritiqueItem] = []
        for index, proposal in enumerate(response.value.items, start=1):
            proposal_data = proposal.model_dump(mode="python")
            item_id = stable_id(
                "critique",
                self.profile_id,
                version.version_id,
                round_index,
                index,
                proposal.issue_code,
                proposal.target_path,
            )
            items.append(
                CritiqueItem(
                    critique_id=item_id,
                    source=CritiqueSource.CRITIC,
                    critic_profile_id=self.profile_id,
                    status=CritiqueStatus.PROPOSED,
                    introduced_in_round=round_index,
                    **proposal_data,
                )
            )
        batch = CritiqueBatch(
            batch_id=stable_id(
                "batch", self.profile_id, version.version_id, round_index
            ),
            plan_version_id=version.version_id,
            round_index=round_index,
            items=items,
        )
        return AgentOutput(
            value=batch,
            usage=response.usage,
            estimated_cost=response.estimated_cost,
            metadata=response.metadata,
        )


class LiveValidator:
    def __init__(
        self,
        profile: AgentProfile,
        provider: OpenAICompatibleProvider,
        prompt_root: Path | None = None,
    ) -> None:
        self.profile = profile
        self.profile_id = profile.profile_id
        self.provider = provider
        self.prompt = load_prompt(profile.prompt_id, prompt_root)

    def validate(
        self,
        task: LessonTask,
        version: LessonPlanVersion,
        critiques: CritiqueBatch,
        round_index: int,
        knowledge: KnowledgeBundle | None = None,
    ) -> AgentOutput[ValidationBatch]:
        required_ids = [item.critique_id for item in critiques.items]
        expected_ids = set(required_ids)
        if len(required_ids) != len(expected_ids):
            raise ValueError("validator input contains duplicate critique_id values")

        def validate(proposals: ValidationProposalSet) -> None:
            actual = [item.critique_id for item in proposals.decisions]
            actual_ids = set(actual)
            missing = sorted(expected_ids - actual_ids)
            unexpected = sorted(actual_ids - expected_ids)
            duplicates = sorted(key for key, count in Counter(actual).items() if count > 1)
            if missing or unexpected or duplicates:
                raise ValueError(
                    "validator must return exactly one decision for every critique; "
                    f"expected_count={len(required_ids)}, actual_count={len(actual)}; "
                    f"missing_ids={missing}; duplicate_ids={duplicates}; "
                    f"unexpected_ids={unexpected}. "
                    "Return one decision for every required_critique_id, including "
                    "defer when evidence is insufficient. Copy IDs exactly."
                )
            by_id = {item.critique_id: item for item in proposals.decisions}
            for item in proposals.decisions:
                if item.decision == ValidationDecisionKind.MERGE:
                    target = by_id.get(item.canonical_critique_id)
                    if target is None or target.decision != ValidationDecisionKind.ACCEPT:
                        accepted_ids = sorted(
                            key for key, value in by_id.items()
                            if value.decision == ValidationDecisionKind.ACCEPT
                        )
                        target_decision = target.decision.value if target else "missing"
                        raise ValueError(
                            f"Invalid merge for critique {item.critique_id!r}: target "
                            f"{item.canonical_critique_id!r} has decision {target_decision!r}. "
                            "The merge target must be accepted in the same batch. "
                            f"Current accepted target IDs: {accepted_ids}. "
                            "Choose a matching accepted target, or give this critique its "
                            "own accept/reject/defer decision and clear canonical_critique_id. "
                            "Do not accept a target merely to satisfy the merge constraint."
                        )

        response = self.provider.invoke_structured(
            prompt=self.prompt,
            input_payload=_payload(
                task=task,
                profile=self.profile,
                knowledge=knowledge,
                current_version=version.model_dump(mode="json"),
                critique_batch=critiques.model_dump(mode="json"),
                required_critique_ids=required_ids,
                required_decision_count=len(required_ids),
                round_index=round_index,
            ),
            output_schema=ValidationProposalSet,
            stage="validator",
            result_validator=validate,
        )
        decisions = [
            ValidationDecision(
                decision_id=stable_id(
                    "decision", critiques.batch_id, proposal.critique_id
                ),
                **proposal.model_dump(mode="python"),
            )
            for proposal in response.value.decisions
        ]
        # An LLM cannot turn a missing authoritative source into an executable
        # edit.  Apply a deterministic, downgrade-only evidence gate before
        # lifecycle transitions can forward such an ACCEPT to Rewriter.
        decisions = enforce_task_evidence_constraints(critiques, decisions, task)
        # The Validator prompt asks for at most five high-leverage accepts per
        # round.  Enforce that structurally (here, before the batch is recorded
        # and applied) so a rewrite round stays focused instead of turning the
        # Rewriter into a thirteen-patch editor.
        blocking_locations = {
            "/" + item.location.replace(".", "/")
            for item in version.rule_check_report.violations
            if item.severity.value in {"high", "critical"}
        }
        blocking_critiques = {
            item.critique_id
            for item in critiques.items
            if any(
                item.target_path == path
                or item.target_path.startswith(path + "/")
                or path.startswith(item.target_path + "/")
                for path in blocking_locations
            )
        }
        decisions = enforce_acceptance_cap(
            decisions,
            max_accepts=DEFAULT_MAX_ACCEPTS_PER_ROUND,
            priority_critique_ids=blocking_critiques,
        )
        batch = ValidationBatch(
            batch_id=stable_id("validation", critiques.batch_id, round_index),
            critique_batch_id=critiques.batch_id,
            round_index=round_index,
            decisions=decisions,
        )
        # Run the same invariant check used by the graph before returning.
        apply_validation(critiques, batch)
        return AgentOutput(
            value=batch,
            usage=response.usage,
            estimated_cost=response.estimated_cost,
            metadata=response.metadata,
        )


class LiveJudge:
    def __init__(
        self,
        profile: AgentProfile,
        provider: OpenAICompatibleProvider,
        prompt_root: Path | None = None,
    ) -> None:
        self.profile = profile
        self.profile_id = profile.profile_id
        self.provider = provider
        self.prompt = load_prompt(profile.prompt_id, prompt_root)

    def compare_optimization(
        self,
        task: LessonTask,
        baseline: LessonPlanVersion,
        candidate: LessonPlanVersion,
    ) -> AgentOutput[PairwiseComparison]:
        """Independently compare a revision with its baseline in both orders."""

        return compare(
            self.provider, task, baseline, candidate,
            prompt_root=self.prompt.path.parent,
        )

    def evaluate(
        self,
        task: LessonTask,
        version: LessonPlanVersion,
        unresolved_issue_count: int,
        knowledge: KnowledgeBundle | None = None,
    ) -> AgentOutput[EvaluationReport]:
        def validate(assessment: JudgeAssessment) -> None:
            scores = assessment.rubric_scores
            signals = assessment.quality_signals
            if signals.genericity_risk >= 7 and (
                scores.teaching_logic > 6.5 or scores.student_engagement > 6.5
            ):
                raise ValueError("judge score violates the genericity cap")
            if signals.material_readiness <= 4 and (
                scores.classroom_feasibility > 7 or scores.assessment_design > 7
            ):
                raise ValueError("judge score violates the material-readiness cap")
            if signals.disciplinary_depth <= 4 and (
                scores.knowledge_accuracy >= 9 or scores.teaching_logic >= 9
            ):
                raise ValueError("judge score violates the disciplinary-depth cap")

        response = self.provider.invoke_structured(
            prompt=self.prompt,
            input_payload=_payload(
                task=task,
                profile=self.profile,
                knowledge=knowledge,
                current_version=version.model_dump(mode="json"),
                deterministic_rule_report=version.rule_check_report.model_dump(
                    mode="json"
                ),
                unresolved_issue_count=unresolved_issue_count,
                task_evidence_profile=build_task_evidence_profile(task),
            ),
            output_schema=JudgeAssessment,
            stage="judge",
            result_validator=validate,
        )
        scores = response.value.rubric_scores
        report = EvaluationReport(
            evaluation_id=stable_id("evaluation", version.version_id, version.document_hash),
            evaluated_version_id=version.version_id,
            rubric_id=task.rubric_id,
            rubric_scores=scores,
            quality_signals=response.value.quality_signals,
            overall_score=round(sum(scores.values_list()) / 8, 3),
            high_risk_issue_ids=response.value.high_risk_issue_ids,
            unresolved_issue_count=unresolved_issue_count,
            rule_checks_passed=version.rule_check_report.passed,
            recommended_action=response.value.recommended_action,
            summary=response.value.summary,
        )
        return AgentOutput(
            value=report,
            usage=response.usage,
            estimated_cost=response.estimated_cost,
            metadata=response.metadata,
        )


class LiveRewriter:
    uses_per_critique_patches = True
    def __init__(
        self,
        profile: AgentProfile,
        provider: OpenAICompatibleProvider,
        prompt_root: Path | None = None,
        *,
        duration_tolerance_minutes: int = 2,
    ) -> None:
        self.profile = profile
        self.profile_id = profile.profile_id
        self.provider = provider
        self.prompt = load_prompt(profile.prompt_id, prompt_root)
        # Same tolerance as the graph's rewrite rule report (see LiveWriter).
        self.duration_tolerance_minutes = duration_tolerance_minutes

    def rewrite(
        self,
        task: LessonTask,
        version: LessonPlanVersion,
        accepted_critiques: list[CritiqueItem],
        round_index: int,
        knowledge: KnowledgeBundle | None = None,
    ) -> AgentOutput[RewriteOutcome]:
        accepted_by_id = {item.critique_id: item for item in accepted_critiques}
        if len(accepted_by_id) != len(accepted_critiques):
            raise ValueError("rewriter input contains duplicate critique IDs")

        # Optimization is transactional: an existing lesson must never be
        # re-emitted wholesale merely because a critic points to a list root.
        # Generation keeps its coherent full-document rewrite route.
        if task.mode.value == "optimize":
            return incremental_patch_rewrite(
                self.provider, task, version, accepted_critiques, round_index,
                self.duration_tolerance_minutes,
            )

        def validate(outcome: RewriteOutcome) -> None:
            original = version.document
            candidate = outcome.document
            if candidate.task_id != original.task_id or candidate.plan_id != original.plan_id:
                raise ValueError("rewriter changed immutable plan identity")
            if candidate.metadata != original.metadata:
                raise ValueError("rewriter changed immutable lesson metadata")
            changed = {item.critique_id for item in outcome.changes}
            unresolved = set(outcome.unresolved_critique_ids)
            if changed | unresolved != set(accepted_by_id) or changed & unresolved:
                raise ValueError(
                    "every accepted critique must map to one change or unresolved ID"
                )
            for change in outcome.changes:
                expected = accepted_by_id[change.critique_id].target_path
                if change.target_path != expected:
                    raise ValueError(
                        f"change target mismatch for {change.critique_id}: {expected}"
                    )
                if not change.edited_paths or len(change.edited_paths) != len(set(change.edited_paths)):
                    raise ValueError(
                        f"rewriter must identify distinct actual edit paths: {change.critique_id}"
                    )
                for edited_path in change.edited_paths:
                    if not edited_path.startswith("/") or edited_path.startswith(
                        ("/metadata", "/task_id", "/plan_id", "/schema_version", "/template_id")
                    ):
                        raise ValueError(f"rewriter used forbidden edit path: {edited_path}")
                    if not lesson_target_changed(original, candidate, edited_path):
                        raise ValueError(
                            "rewriter claimed a change but its edited field did not change: "
                            f"{change.critique_id} -> {edited_path}"
                        )
            if not outcome.changes and candidate != original:
                raise ValueError(
                    "rewriter changed the document without an accepted critique mapping"
                )
            report = check_lesson_plan(
                candidate,
                task,
                duration_tolerance_minutes=self.duration_tolerance_minutes,
            )
            if not report.passed:
                raise ValueError("rewriter output failed deterministic hard rules")

        response = self.provider.invoke_structured(
            prompt=self.prompt,
            input_payload=_payload(
                task=task,
                profile=self.profile,
                knowledge=knowledge,
                current_version=version.model_dump(mode="json"),
                accepted_critiques=[
                    item.model_dump(mode="json") for item in accepted_critiques
                ],
                round_index=round_index,
            ),
            output_schema=RewriteOutcome,
            stage="rewriter",
            result_validator=validate,
        )
        return AgentOutput(
            value=response.value,
            usage=response.usage,
            estimated_cost=response.estimated_cost,
            metadata=response.metadata,
        )


def build_live_suite(
    config: ExperimentConfig,
    prompt_root: Path | None = None,
) -> AgentSuite:
    profiles = default_profile_registry(config.role_model_configs)

    def provider(profile_id: str) -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider(profiles[profile_id].model)

    return AgentSuite(
        execution_mode="live",
        profiles=profiles,
        designer=LiveDesignArchitect(
            profiles[config.designer_profile_id],
            provider(config.designer_profile_id),
            prompt_root,
        ),
        writer=LiveWriter(
            profiles[config.writer_profile_id],
            provider(config.writer_profile_id),
            prompt_root,
            duration_tolerance_minutes=config.duration_tolerance_minutes,
        ),
        critics=[
            LiveCritic(profiles[profile_id], provider(profile_id), prompt_root)
            for profile_id in config.critic_profile_ids
        ],
        validator=LiveValidator(
            profiles[config.validator_profile_id],
            provider(config.validator_profile_id),
            prompt_root,
        ),
        judge=LiveJudge(
            profiles[config.judge_profile_id],
            provider(config.judge_profile_id),
            prompt_root,
        ),
        rewriter=LiveRewriter(
            profiles[config.rewriter_profile_id],
            provider(config.rewriter_profile_id),
            prompt_root,
            duration_tolerance_minutes=config.duration_tolerance_minutes,
        ),
    )
