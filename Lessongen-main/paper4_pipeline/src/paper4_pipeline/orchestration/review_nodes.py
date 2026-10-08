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


class _NodeExecutionError(RuntimeError):
    """A multi-call node failure with all in-node usage preserved for projection."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        usage: TokenUsage,
        estimated_cost: float,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.usage = usage
        self.estimated_cost = estimated_cost


class ReviewNodes:
    def _judge(self, state: PipelineState) -> PipelineState:
        started = perf_counter()
        task = self._task(state)
        config = self._config(state)
        current = self._current_version(state)
        history = self._critique_history(state)
        unresolved_statuses = {
            CritiqueStatus.ACCEPTED,
            CritiqueStatus.PARTIALLY_IMPLEMENTED,
            CritiqueStatus.UNRESOLVED,
            CritiqueStatus.REOPENED,
            CritiqueStatus.REGRESSION,
        }
        unresolved = sum(item.status in unresolved_statuses for item in history)
        profile = self._profiles[config.judge_profile_id]
        knowledge = build_knowledge_bundle(profile, task)
        output = self.agents.judge.evaluate(
            task, current, unresolved, knowledge
        )
        regressions = [
            item.critique_id
            for item in history
            if item.status == CritiqueStatus.REGRESSION
        ]
        report_data = output.value.model_dump(mode="python")
        report_data["regressions"] = regressions
        report_data["unresolved_issue_count"] = unresolved
        report = EvaluationReport.model_validate(report_data)
        version_data = current.model_dump(mode="python")
        version_data["internal_evaluation"] = report
        updated_current = LessonPlanVersion.model_validate(version_data)
        versions = [
            updated_current if item.version_id == current.version_id else item
            for item in self._versions(state)
        ]
        selection = select_best_version(
            versions, config,
            dedupe_equivalent_content=self._task(state).mode == TaskMode.OPTIMIZE,
            task_mode=task.mode,
        )
        usage = self._sum_usage(self._usage(state), output.usage)
        cost = state["estimated_cost"] + output.estimated_cost
        self._trace(state).append(
            event_type="judge_completed",
            stage="judge",
            actor_profile_id=self.agents.judge.profile_id,
            knowledge_bundle_id=knowledge.bundle_id,
            round_index=current.iteration,
            version_id=current.version_id,
            input_summary={
                "document_hash": current.document_hash,
                "rule_report": current.rule_check_report.model_dump(mode="json"),
                "unresolved_issue_count": unresolved,
                "task_evidence_profile": build_task_evidence_profile(task),
                "agent_profile": profile.model_dump(mode="json"),
                "knowledge_bundle": knowledge.model_dump(mode="json"),
            },
            output_summary={
                "evaluation": report.model_dump(mode="json"),
                "version_selection": selection.model_dump(mode="json"),
                "model_call": self._call_metadata(output),
            },
            token_usage=output.usage,
            estimated_cost=output.estimated_cost,
            duration_seconds=perf_counter() - started,
        )
        return {
            "versions": [item.model_dump(mode="json") for item in versions],
            "version_selections": [
                *state["version_selections"],
                selection.model_dump(mode="json"),
            ],
            "model_call_count": state["model_call_count"]
            + self._attempt_count(output),
            "token_usage": usage.model_dump(mode="json"),
            "estimated_cost": cost,
            "knowledge_bundles": [
                *state["knowledge_bundles"],
                knowledge.model_dump(mode="json"),
            ],
        }


    def _evaluation_router(self, state: PipelineState) -> PipelineState:
        current = self._current_version(state)
        assert current.internal_evaluation is not None
        config = self._config(state)
        task = self._task(state)
        score_deltas = list(state["score_deltas"])
        pending = state.get("pending_iteration")
        if pending:
            parent = self._version_by_id(state, str(pending["input_version_id"]))
            assert parent.internal_evaluation is not None
            score_deltas.append(
                current.internal_evaluation.overall_score
                - parent.internal_evaluation.overall_score
            )
        require_initial_review = current.iteration == 0 and (
            task.mode == TaskMode.OPTIMIZE
            or config.generation_review_policy == "at_least_one_independent_review"
        )
        review_profiles = [
            *(critic.profile_id for critic in self.agents.critics),
            config.validator_profile_id,
        ]
        next_profiles = [*review_profiles, config.judge_profile_id]
        if task.mode != TaskMode.OPTIMIZE or not getattr(
            self.agents.rewriter, "uses_per_critique_patches", False,
        ):
            next_profiles.append(config.rewriter_profile_id)
        required_calls = self._worst_case_attempts(
            config, review_profiles if require_initial_review else next_profiles
        )
        if not require_initial_review and task.mode == TaskMode.OPTIMIZE and getattr(
            self.agents.rewriter, "uses_per_critique_patches", False,
        ):
            required_calls += DEFAULT_MAX_ACCEPTS_PER_ROUND
        decision = route_after_evaluation(
            report=current.internal_evaluation,
            rule_report=current.rule_check_report,
            versions=self._versions(state),
            config=config,
            model_call_count=state["model_call_count"],
            token_usage=self._usage(state),
            estimated_cost=state["estimated_cost"],
            score_deltas=score_deltas,
            required_next_model_calls=required_calls,
            elapsed_seconds=self._elapsed_seconds(state),
            require_initial_review=require_initial_review,
            task_mode=task.mode,
        )
        routes = [*state["route_decisions"], decision.model_dump(mode="json")]
        iterations = list(state["iterations"])
        if pending:
            start_usage = TokenUsage.model_validate(pending["start_token_usage"])
            total_usage = self._usage(state)
            iteration = IterationRecord(
                iteration_id=str(pending["iteration_id"]),
                round_index=current.iteration,
                input_version_id=str(pending["input_version_id"]),
                output_version_id=current.version_id,
                critique_ids=list(pending["critique_ids"]),
                validation_decision_ids=list(pending["validation_decision_ids"]),
                evaluation_id=current.internal_evaluation.evaluation_id,
                rewrite_id=str(pending["rewrite_id"]),
                regressions=list(current.internal_evaluation.regressions),
                score_delta=score_deltas[-1],
                duration_seconds=max(
                    0.0,
                    self._elapsed_from_iso(str(pending["started_at"])),
                ),
                token_usage=TokenUsage(
                    input_tokens=max(
                        0, total_usage.input_tokens - start_usage.input_tokens
                    ),
                    output_tokens=max(
                        0, total_usage.output_tokens - start_usage.output_tokens
                    ),
                ),
                estimated_cost=max(
                    0.0,
                    state["estimated_cost"] - float(pending["start_cost"]),
                ),
                route=decision.next_action,
                route_decision_id=decision.decision_id,
            )
            iterations.append(iteration.model_dump(mode="json"))
        self._trace(state).append(
            event_type="route_decided",
            stage="evaluation_router",
            round_index=current.iteration,
            version_id=current.version_id,
            input_summary={
                "evaluation_id": current.internal_evaluation.evaluation_id,
                "model_call_count": state["model_call_count"],
                "token_usage": state["token_usage"],
                "elapsed_seconds": self._elapsed_seconds(state),
                "generation_review_policy": config.generation_review_policy,
                "initial_review_pending": require_initial_review,
            },
            output_summary=decision.model_dump(mode="json"),
        )
        return {
            "route_decisions": routes,
            "iterations": iterations,
            "score_deltas": score_deltas,
            "pending_iteration": None,
            "stop_reason": decision.primary_reason.value
            if decision.primary_reason
            else None,
        }


    def _critics(self, state: PipelineState) -> PipelineState:
        started = perf_counter()
        cycle_started_at = self._aware_now().isoformat()
        task = self._task(state)
        current = self._current_version(state)
        round_index = current.iteration + 1
        config = self._config(state)
        history = self._critique_history(state)
        calls = state["model_call_count"]
        usage = self._usage(state)
        cost = state["estimated_cost"]
        bundles = list(state["knowledge_bundles"])
        all_items: list[CritiqueItem] = []
        node_attempts = 0
        node_usage = TokenUsage()
        node_cost = 0.0
        for critic in self.agents.critics:
            profile = self._profiles[critic.profile_id]
            knowledge = build_knowledge_bundle(profile, task)
            try:
                output = critic.review(
                    task,
                    current,
                    round_index,
                    knowledge,
                    prior_critiques=history,
                )
            except Exception as exc:
                failed_attempts = int(getattr(exc, "attempts", 0))
                failed_usage = getattr(exc, "usage", TokenUsage())
                if not isinstance(failed_usage, TokenUsage):
                    failed_usage = TokenUsage()
                failed_cost = float(getattr(exc, "estimated_cost", 0.0))
                self._trace(state).append(
                    event_type="critic_failed",
                    stage="critics",
                    actor_profile_id=critic.profile_id,
                    knowledge_bundle_id=knowledge.bundle_id,
                    round_index=round_index,
                    version_id=current.version_id,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                    token_usage=failed_usage,
                    estimated_cost=failed_cost,
                    duration_seconds=perf_counter() - started,
                )
                raise _NodeExecutionError(
                    f"critic {critic.profile_id} failed: {type(exc).__name__}: {exc}",
                    attempts=node_attempts + failed_attempts,
                    usage=self._sum_usage(node_usage, failed_usage),
                    estimated_cost=node_cost + failed_cost,
                ) from exc
            attempt_count = self._attempt_count(output)
            node_attempts += attempt_count
            node_usage = self._sum_usage(node_usage, output.usage)
            node_cost += output.estimated_cost
            calls += attempt_count
            usage = self._sum_usage(usage, output.usage)
            cost += output.estimated_cost
            bundles.append(knowledge.model_dump(mode="json"))
            all_items.extend(output.value.items)
            self._trace(state).append(
                event_type="critic_completed",
                stage="critics",
                actor_profile_id=critic.profile_id,
                knowledge_bundle_id=knowledge.bundle_id,
                round_index=round_index,
                version_id=current.version_id,
                input_summary={
                    "document_hash": current.document_hash,
                    "agent_profile": profile.model_dump(mode="json"),
                    "knowledge_bundle": knowledge.model_dump(mode="json"),
                    "prior_critique_statuses": {
                        item.critique_id: item.status.value for item in history
                    },
                },
                output_summary={
                    "critique_batch": output.value.model_dump(mode="json"),
                    "model_call": self._call_metadata(output),
                },
                token_usage=output.usage,
                estimated_cost=output.estimated_cost,
            )
        reopened_history, reopened = reopen_cap_deferred_for_validation(
            history,
            round_index=round_index,
            version_id=current.version_id,
            exclude_ids={item.critique_id for item in all_items},
        )
        combined = CritiqueBatch(
            batch_id=stable_id("combined", current.version_id, round_index),
            plan_version_id=current.version_id,
            round_index=round_index,
            items=[*all_items, *reopened],
        )
        self._trace(state).append(
            event_type="critiques_aggregated",
            stage="critique_aggregator",
            round_index=round_index,
            version_id=current.version_id,
            output_summary={
                "critique_batch": combined.model_dump(mode="json"),
                "reopened_cap_deferred_ids": [
                    item.critique_id for item in reopened
                ],
            },
            duration_seconds=perf_counter() - started,
        )
        return {
            "current_critique_batch": combined.model_dump(mode="json"),
            "critique_history": [
                item.model_dump(mode="json") for item in reopened_history
            ],
            "model_call_count": calls,
            "token_usage": usage.model_dump(mode="json"),
            "estimated_cost": cost,
            "knowledge_bundles": bundles,
            "cycle_start": {
                "started_at": cycle_started_at,
                "token_usage": state["token_usage"],
                "cost": state["estimated_cost"],
            },
        }


    def _validator(self, state: PipelineState) -> PipelineState:
        started = perf_counter()
        task = self._task(state)
        config = self._config(state)
        current = self._current_version(state)
        batch = self._current_batch(state)
        profile = self._profiles[config.validator_profile_id]
        knowledge = build_knowledge_bundle(profile, task)
        output = self.agents.validator.validate(
            task, current, batch, batch.round_index, knowledge
        )
        validated = apply_validation(batch, output.value)
        history = merge_critique_history(self._critique_history(state), validated)
        usage = self._sum_usage(self._usage(state), output.usage)
        self._trace(state).append(
            event_type="validation_completed",
            stage="validator",
            actor_profile_id=self.agents.validator.profile_id,
            knowledge_bundle_id=knowledge.bundle_id,
            round_index=batch.round_index,
            version_id=current.version_id,
            input_summary={
                "critique_batch": batch.model_dump(mode="json"),
                "agent_profile": profile.model_dump(mode="json"),
                "knowledge_bundle": knowledge.model_dump(mode="json"),
            },
            output_summary={
                "decisions": output.value.model_dump(mode="json"),
                "critique_lifecycle": validated.model_dump(mode="json"),
                "model_call": self._call_metadata(output),
            },
            token_usage=output.usage,
            estimated_cost=output.estimated_cost,
            duration_seconds=perf_counter() - started,
        )
        return {
            "current_critique_batch": validated.model_dump(mode="json"),
            "critique_history": [item.model_dump(mode="json") for item in history],
            "validation_batches": [
                *state["validation_batches"],
                output.value.model_dump(mode="json"),
            ],
            "model_call_count": state["model_call_count"]
            + self._attempt_count(output),
            "token_usage": usage.model_dump(mode="json"),
            "estimated_cost": state["estimated_cost"] + output.estimated_cost,
            "knowledge_bundles": [
                *state["knowledge_bundles"],
                knowledge.model_dump(mode="json"),
            ],
        }


    def _validation_router(self, state: PipelineState) -> PipelineState:
        batch = self._current_batch(state)
        config = self._config(state)
        task = self._task(state)
        required_calls = self._worst_case_attempts(
            config, [config.rewriter_profile_id, config.judge_profile_id],
        )
        if task.mode.value == "optimize" and getattr(
            self.agents.rewriter, "uses_per_critique_patches", False,
        ):
            # Optimization patches allow one schema-repair retry per accepted
            # critique. Reserve both attempts so the configured call budget
            # remains a hard boundary rather than being exceeded mid-round.
            required_calls = 2 * len(actionable_critiques(batch)) + self._worst_case_attempts(
                config, [config.judge_profile_id],
            )
        decision = route_after_validation(
            critiques=batch,
            config=config,
            model_call_count=state["model_call_count"],
            token_usage=self._usage(state),
            estimated_cost=state["estimated_cost"],
            required_next_model_calls=required_calls,
            elapsed_seconds=self._elapsed_seconds(state),
            max_rounds_hit=(
                batch.round_index > (
                    config.optimization_max_rounds if task.mode == TaskMode.OPTIMIZE
                    else config.max_rounds
                )
            ),
        )
        self._trace(state).append(
            event_type="route_decided",
            stage="validation_router",
            round_index=batch.round_index,
            version_id=batch.plan_version_id,
            input_summary={
                "critique_statuses": {
                    item.critique_id: item.status.value for item in batch.items
                }
            },
            output_summary=decision.model_dump(mode="json"),
        )
        return {
            "route_decisions": [
                *state["route_decisions"],
                decision.model_dump(mode="json"),
            ],
            "stop_reason": decision.primary_reason.value
            if decision.primary_reason
            else None,
        }

