"""LangGraph implementation of the Paper#4 real-model vertical slice."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable

from langgraph.graph import END, START, StateGraph

from paper4_pipeline.agents.profiles import validate_profile_references
from paper4_pipeline.agents.protocols import AgentOutput
from paper4_pipeline.agents.suite import AgentSuite
from paper4_pipeline.control.lifecycle import (
    DEFAULT_MAX_ACCEPTS_PER_ROUND,
    actionable_critiques,
    apply_rewrite_outcome,
    apply_validation,
    detect_regressions,
    merge_critique_history,
    reopen_cap_deferred_for_validation,
    transition_critique,
    verify_rewrite,
)
from paper4_pipeline.control.evidence import build_task_evidence_profile
from paper4_pipeline.control.optimization import content_hash, optimization_quality_gate
from paper4_pipeline.control.routing import (
    route_after_evaluation,
    route_after_validation,
)
from paper4_pipeline.control.rules import check_lesson_plan
from paper4_pipeline.control.versioning import document_hash, select_best_version
from paper4_pipeline.domain.models import (
    CritiqueBatch,
    CritiqueItem,
    CritiqueStatus,
    EvaluationReport,
    ExperimentConfig,
    IterationRecord,
    LessonDesignBlueprint,
    LessonPlanVersion,
    LessonTask,
    PipelineResult,
    RewriteRecord,
    RouteAction,
    RouteDecision,
    RunStatus,
    StopReason,
    TaskMode,
    TokenUsage,
    ValidationBatch,
    VersionSelection,
)
from paper4_pipeline.domain.ids import stable_id
from paper4_pipeline.domain.naming import automatic_run_id
from paper4_pipeline.knowledge.registry import build_knowledge_bundle
from paper4_pipeline.observability.trace import TraceStore
from paper4_pipeline.orchestration.state import PipelineState, assert_json_safe_state


class FinalizationNodes:
    def _finalize(self, state: PipelineState) -> PipelineState:
        decision = RouteDecision.model_validate(state["route_decisions"][-1])
        selection = VersionSelection.model_validate(state["version_selections"][-1])
        updates: PipelineState = {}
        if self._task(state).mode == TaskMode.OPTIMIZE:
            versions = self._versions(state)
            baseline = min(versions, key=lambda item: (item.iteration, item.version_id))
            candidate = next(
                item for item in versions if item.version_id == selection.selected_version_id
            )
            quality_gate = optimization_quality_gate(baseline, candidate, self._config(state))
            updates["optimization_quality_gate"] = quality_gate
            comparator = getattr(self.agents.judge, "compare_optimization", None)
            if (
                callable(comparator)
                and decision.next_action not in {RouteAction.FAIL, RouteAction.ROLLBACK}
                and content_hash(baseline.document) != content_hash(candidate.document)
                and state["model_call_count"] + 2 <= self._config(state).max_model_calls
                and self._usage(state).total_tokens + 80_000
                <= self._config(state).max_total_tokens
                and state["estimated_cost"] + 0.5
                <= self._config(state).max_estimated_cost
            ):
                started = perf_counter()
                comparison_output = comparator(self._task(state), baseline, candidate)
                comparison = comparison_output.value.model_dump(mode="json")
                updates["optimization_comparison"] = comparison
                updates["model_call_count"] = (
                    state["model_call_count"]
                    + (comparison_output.metadata.attempts if comparison_output.metadata else 0)
                )
                updates["token_usage"] = self._sum_usage(
                    self._usage(state), comparison_output.usage
                ).model_dump(mode="json")
                updates["estimated_cost"] = (
                    state["estimated_cost"] + comparison_output.estimated_cost
                )
                self._trace(state).append(
                    event_type="optimization_pairwise_compared",
                    stage="optimization_compare",
                    actor_profile_id=self.agents.judge.profile_id,
                    version_id=candidate.version_id,
                    input_summary={
                        "baseline_version_id": baseline.version_id,
                        "candidate_version_id": candidate.version_id,
                        "changed_sections": comparison["changed_sections"],
                    },
                    output_summary={
                        "comparison": comparison,
                        "model_call": self._call_metadata(comparison_output),
                    },
                    token_usage=comparison_output.usage,
                    estimated_cost=comparison_output.estimated_cost,
                    duration_seconds=perf_counter() - started,
                )
                if (
                    comparison["verdict"] == "baseline_preferred"
                    and baseline.version_id in selection.eligible_candidate_ids
                ):
                    payload = selection.model_dump(mode="python")
                    payload["selected_version_id"] = baseline.version_id
                    payload["requires_human"] = True
                    payload["selection_reason"] = (
                        "双向独立比较均倾向原稿；保留原稿为交付稿，"
                        "修订候选稿仍可供教师对照复核。"
                    )
                    selection = VersionSelection.model_validate(payload)
                    updates["optimization_quality_gate"] = optimization_quality_gate(
                        baseline, baseline, self._config(state)
                    )
                elif comparison["verdict"] == "candidate_preferred" and quality_gate["passed"]:
                    payload = selection.model_dump(mode="python")
                    payload["requires_human"] = False
                    payload["ambiguous_candidate_ids"] = []
                    payload["selection_reason"] = (
                        "真实内容变化通过内部质量门槛，且双向独立比较均偏好修订稿；"
                        "仍非真实课堂效果证明。"
                    )
                    selection = VersionSelection.model_validate(payload)
                updates["version_selections"] = [
                    *state["version_selections"][:-1], selection.model_dump(mode="json")
                ]
            elif content_hash(baseline.document) != content_hash(candidate.document):
                updates["optimization_comparison"] = {
                    "baseline_version_id": baseline.version_id,
                    "candidate_version_id": candidate.version_id,
                    "verdict": "uncertain",
                    "target_issue_progress": "uncertain",
                    "changed_sections": [],
                    "regression_flags": [],
                    "evidence": [],
                    "votes": [],
                    "failed_calls": 0,
                    "reason": (
                        "双顺序对照未执行：比较器不可用。"
                        if not callable(comparator)
                        else "双顺序对照未执行：运行状态或预算不足，修订稿只能待教师复核。"
                    ),
                }
        # ``requires_human`` is set by best-version selection when the top two
        # candidates are statistically tied (or when every candidate was
        # eliminated and the earliest safe draft is a fallback).  Consume it at
        # the final stop: if the run is ending on an ambiguous or fallback
        # choice (and quality was not cleanly passed), surface NEEDS_HUMAN
        # instead of silently exporting an arbitrary pick.
        if decision.next_action in {RouteAction.FAIL, RouteAction.ROLLBACK}:
            # A regression guard has no rollback node in v0.1, so stopping on
            # ROLLBACK is a safety failure, never a false "completed": the run
            # stops and an explicitly named recovery draft is exported for review.
            status = RunStatus.FAILED
        elif decision.next_action == RouteAction.HUMAN_REVIEW or (
            decision.primary_reason in {StopReason.BUDGET_EXCEEDED, StopReason.MAX_ROUNDS}
            and self._task(state).mode == TaskMode.GENERATE
            and (
                not state["validation_batches"]
                or any(
                    item.status == CritiqueStatus.ACCEPTED
                    for item in self._critique_history(state)
                )
            )
        ) or (
            decision.next_action == RouteAction.FINALIZE
            and selection.requires_human
            and (
                self._task(state).mode == TaskMode.OPTIMIZE
                or decision.primary_reason != StopReason.QUALITY_PASSED
            )
        ):
            status = RunStatus.NEEDS_HUMAN
        else:
            status = RunStatus.COMPLETED
        stop_reason = decision.primary_reason or StopReason.RUNTIME_ERROR
        if (
            self._task(state).mode == TaskMode.OPTIMIZE
            and decision.primary_reason == StopReason.QUALITY_PASSED
            and selection.requires_human
        ):
            stop_reason = StopReason.HUMAN_STOP
        self._trace(state).append(
            event_type="run_completed",
            stage="finalize",
            version_id=selection.selected_version_id,
            output_summary={
                "status": status.value,
                "stop_reason": stop_reason.value,
                "best_version_id": selection.selected_version_id,
                "last_version_id": state["current_version_id"],
            },
            status="ok" if status == RunStatus.COMPLETED else status.value,
        )
        return {**updates, "status": status.value, "stop_reason": stop_reason.value}

