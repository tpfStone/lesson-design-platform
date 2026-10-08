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


class DesignBootstrapNodes:
    def _design(self, state: PipelineState) -> PipelineState:
        task = self._task(state)
        if task.mode != TaskMode.GENERATE:
            return {"design_blueprint": None}
        started = perf_counter()
        config = self._config(state)
        profile = self._profiles[config.designer_profile_id]
        knowledge = build_knowledge_bundle(profile, task)
        output = self.agents.designer.design(task, knowledge)
        usage = self._sum_usage(self._usage(state), output.usage)
        self._trace(state).append(
            event_type="design_blueprint_completed",
            stage="design_architect",
            actor_profile_id=self.agents.designer.profile_id,
            knowledge_bundle_id=knowledge.bundle_id,
            input_summary={
                "task": task.model_dump(mode="json"),
                "agent_profile": profile.model_dump(mode="json"),
                "knowledge_bundle": knowledge.model_dump(mode="json"),
            },
            output_summary={
                "design_blueprint": output.value.model_dump(mode="json"),
                "model_call": self._call_metadata(output),
            },
            token_usage=output.usage,
            estimated_cost=output.estimated_cost,
            duration_seconds=perf_counter() - started,
        )
        return {
            "design_blueprint": output.value.model_dump(mode="json"),
            "model_call_count": state["model_call_count"]
            + self._attempt_count(output),
            "token_usage": usage.model_dump(mode="json"),
            "estimated_cost": state["estimated_cost"] + output.estimated_cost,
            "knowledge_bundles": [
                *state["knowledge_bundles"],
                knowledge.model_dump(mode="json"),
            ],
        }


    def _bootstrap(self, state: PipelineState) -> PipelineState:
        started = perf_counter()
        task = self._task(state)
        config = self._config(state)
        calls = state["model_call_count"]
        usage = self._usage(state)
        cost = state["estimated_cost"]
        bundles = list(state["knowledge_bundles"])
        if task.mode == TaskMode.GENERATE:
            profile = self._profiles[config.writer_profile_id]
            knowledge = build_knowledge_bundle(profile, task)
            blueprint = LessonDesignBlueprint.model_validate(
                state["design_blueprint"]
            )
            output = self.agents.writer.generate(task, knowledge, blueprint)
            document = output.value
            calls += self._attempt_count(output)
            usage = self._sum_usage(usage, output.usage)
            cost += output.estimated_cost
            bundles.append(knowledge.model_dump(mode="json"))
            actor = self.agents.writer.profile_id
            event_type = "writer_completed"
            trace_input = {
                "task": task.model_dump(mode="json"),
                "agent_profile": profile.model_dump(mode="json"),
                "knowledge_bundle": knowledge.model_dump(mode="json"),
            }
            trace_output = document.model_dump(mode="json")
            call_usage = output.usage
            call_cost = output.estimated_cost
            knowledge_id = knowledge.bundle_id
            call_metadata = self._call_metadata(output)
        else:
            assert task.initial_plan is not None
            document = task.initial_plan
            actor = "human_input"
            event_type = "input_version_registered"
            trace_input = {"task_mode": task.mode.value}
            trace_output = document.model_dump(mode="json")
            call_usage = TokenUsage()
            call_cost = 0.0
            knowledge_id = ""
            call_metadata = None

        rule_report = check_lesson_plan(
            document,
            task,
            config.duration_tolerance_minutes,
            report_id=f"rule-v0",
        )
        version = LessonPlanVersion(
            version_id="v0",
            iteration=0,
            document=document,
            created_by_profile_id=actor,
            created_at=self._aware_now(),
            document_hash=document_hash(document),
            rule_check_report=rule_report,
            diff_summary="初始生成稿" if task.mode == TaskMode.GENERATE else "用户输入稿",
            estimated_cost=cost,
        )
        self._trace(state).append(
            event_type=event_type,
            stage="bootstrap",
            actor_profile_id=actor,
            knowledge_bundle_id=knowledge_id,
            version_id=version.version_id,
            input_summary=trace_input,
            output_summary={
                "document": trace_output,
                "rule_report": rule_report.model_dump(mode="json"),
                "model_call": call_metadata,
            },
            token_usage=call_usage,
            estimated_cost=call_cost,
            duration_seconds=perf_counter() - started,
        )
        return {
            "versions": [version.model_dump(mode="json")],
            "current_version_id": version.version_id,
            "model_call_count": calls,
            "token_usage": usage.model_dump(mode="json"),
            "estimated_cost": cost,
            "knowledge_bundles": bundles,
        }

