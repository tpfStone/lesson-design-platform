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
from paper4_pipeline.observability.call_ledger import activate_call_ledger
from paper4_pipeline.orchestration.design_nodes import DesignBootstrapNodes
from paper4_pipeline.orchestration.review_nodes import ReviewNodes
from paper4_pipeline.orchestration.revision_nodes import RevisionNodes
from paper4_pipeline.orchestration.finalization_nodes import FinalizationNodes
from paper4_pipeline.orchestration.state import PipelineState, assert_json_safe_state




class Paper4Workflow(DesignBootstrapNodes, ReviewNodes, RevisionNodes, FinalizationNodes):
    """A reusable graph whose checkpoint state contains JSON values only."""

    def __init__(
        self,
        agents: AgentSuite,
        output_root: Path,
        clock: Callable[[], datetime] | None = None,
        run_id_factory: Callable[[LessonTask], str] | None = None,
    ) -> None:
        self.agents = agents
        self.output_root = output_root.resolve()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._run_id_factory = run_id_factory or (
            lambda task: automatic_run_id(task, now=self._aware_now().astimezone())
        )
        self._profiles = agents.profiles
        self._traces: dict[str, TraceStore] = {}
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(PipelineState)
        builder.add_node("design", self._design)
        builder.add_node("bootstrap", self._bootstrap)
        builder.add_node("judge", self._judge)
        builder.add_node("evaluation_router", self._evaluation_router)
        builder.add_node("critics", self._critics)
        builder.add_node("validator", self._validator)
        builder.add_node("validation_router", self._validation_router)
        builder.add_node("rewriter", self._rewriter)
        builder.add_node("verifier", self._verifier)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "design")
        builder.add_edge("design", "bootstrap")
        builder.add_edge("bootstrap", "judge")
        builder.add_edge("judge", "evaluation_router")
        builder.add_conditional_edges(
            "evaluation_router",
            self._evaluation_edge,
            {"review": "critics", "finish": "finalize"},
        )
        builder.add_edge("critics", "validator")
        builder.add_edge("validator", "validation_router")
        builder.add_conditional_edges(
            "validation_router",
            self._validation_edge,
            {"rewrite": "rewriter", "finish": "finalize"},
        )
        builder.add_conditional_edges(
            "rewriter",
            self._rewrite_edge,
            {"rewrite_ok": "verifier", "rewrite_failed": "finalize"},
        )
        builder.add_edge("verifier", "judge")
        builder.add_edge("finalize", END)
        return builder.compile()

    def run(
        self,
        task: LessonTask,
        config: ExperimentConfig,
        run_id: str | None = None,
    ) -> PipelineResult:
        config = self._effective_config(task, config)
        if config.execution_mode != self.agents.execution_mode:
            raise ValueError(
                "workflow and agent suite execution modes do not match: "
                f"{config.execution_mode!r} != {self.agents.execution_mode!r}"
            )
        if config.interaction_protocol != "independent_review":
            raise ValueError(
                "v0.1 implements only interaction_protocol='independent_review'"
            )
        if config.knowledge_policy != "heterogeneous":
            raise ValueError("v0.1 currently implements only heterogeneous knowledge")
        if config.enable_paper3:
            raise ValueError(
                "Paper#3 is available as an adapter but is not enabled in the v0.1 graph"
            )
        profile_ids = [
            config.designer_profile_id,
            config.writer_profile_id,
            *config.critic_profile_ids,
            config.validator_profile_id,
            config.judge_profile_id,
            config.rewriter_profile_id,
        ]
        validate_profile_references(profile_ids, self._profiles)
        bootstrap_profile_ids = [config.judge_profile_id]
        if task.mode == TaskMode.GENERATE:
            bootstrap_profile_ids = [
                config.designer_profile_id,
                config.writer_profile_id,
                config.judge_profile_id,
            ]
        bootstrap_attempt_reserve = self._worst_case_attempts(
            config, bootstrap_profile_ids
        )
        if config.max_model_calls < bootstrap_attempt_reserve:
            raise ValueError(
                "max_model_calls is too small for the initial pipeline with retries: "
                f"need at least {bootstrap_attempt_reserve}, got {config.max_model_calls}"
            )
        actual_run_id = run_id or self._run_id_factory(task)
        workspace = self.output_root / actual_run_id
        reserved_outputs = (
            "trace.jsonl",
            "run_result.json",
            "manifest.json",
            "best_lesson_plan.json",
            "best_lesson_plan.md",
            "best_lesson_plan.docx",
            "optimization_report.json",
            "optimization_report.md",
            "recovery_lesson_plan.json",
            "recovery_lesson_plan.md",
            "model_call_ledger.jsonl",
        )
        collisions = [name for name in reserved_outputs if (workspace / name).exists()]
        if collisions:
            raise FileExistsError(
                f"run_id {actual_run_id!r} already contains run artifacts: {collisions}; "
                "use a new run_id to keep traces and outputs isolated"
            )
        trace = TraceStore(workspace, actual_run_id, task.task_id, self._clock)
        self._traces[actual_run_id] = trace
        started_at = self._aware_now().isoformat()
        initial: PipelineState = {
            "schema_version": "paper4-graph-state-v0.1",
            "run_id": actual_run_id,
            "task": task.model_dump(mode="json"),
            "config": config.model_dump(mode="json"),
            "started_at": started_at,
            "workspace_dir": str(workspace),
            "trace_path": str(trace.path),
            "design_blueprint": None,
            "versions": [],
            "critique_history": [],
            "current_critique_batch": None,
            "validation_batches": [],
            "rewrite_records": [],
            "route_decisions": [],
            "version_selections": [],
            "iterations": [],
            "optimization_quality_gate": None,
            "optimization_comparison": None,
            "knowledge_bundles": [],
            "model_call_count": 0,
            "token_usage": TokenUsage().model_dump(mode="json"),
            "estimated_cost": 0.0,
            "score_deltas": [],
            "cycle_start": None,
            "pending_iteration": None,
            "stop_reason": None,
            "status": RunStatus.RUNNING.value,
            "errors": [],
        }
        assert_json_safe_state(initial)
        trace.append(
            event_type="run_started",
            stage="run",
            input_summary={
                "task": task.model_dump(mode="json"),
                "experiment_config": config.model_dump(mode="json"),
                "profile_ids": profile_ids,
            },
        )
        last_state = initial
        with activate_call_ledger(workspace / "model_call_ledger.jsonl") as ledger:
            try:
                for snapshot in self.graph.stream(initial, stream_mode="values"):
                    last_state = snapshot
                    assert_json_safe_state(last_state)
            except Exception as exc:  # preserve trace and last completed graph snapshot
                message = f"{type(exc).__name__}: {exc}"
                failed_attempts = int(getattr(exc, "attempts", 0))
                failed_usage = getattr(exc, "usage", TokenUsage())
                if not isinstance(failed_usage, TokenUsage):
                    failed_usage = TokenUsage()
                failed_cost = float(getattr(exc, "estimated_cost", 0.0))
                trace.append(
                    event_type="run_failed",
                    stage="run",
                    status="error",
                    error=message,
                    output_summary={"last_completed_state_status": last_state.get("status")},
                    token_usage=failed_usage,
                    estimated_cost=failed_cost,
                )
                last_state = {
                    **last_state,
                    "status": RunStatus.FAILED.value,
                    "stop_reason": StopReason.RUNTIME_ERROR.value,
                    "errors": [*last_state.get("errors", []), message],
                    "model_call_count": last_state.get("model_call_count", 0)
                    + failed_attempts,
                    "token_usage": self._sum_usage(
                        self._usage(last_state), failed_usage
                    ).model_dump(mode="json"),
                    "estimated_cost": last_state.get("estimated_cost", 0.0)
                    + failed_cost,
                }
            finally:
                self._traces.pop(actual_run_id, None)
        result = self._project_result(last_state)
        result.model_calls = list(ledger.records)
        return result












    @staticmethod
    def _evaluation_edge(state: PipelineState) -> str:
        decision = RouteDecision.model_validate(state["route_decisions"][-1])
        return "review" if decision.next_action == RouteAction.CONTINUE_REVIEW else "finish"

    @staticmethod
    def _validation_edge(state: PipelineState) -> str:
        decision = RouteDecision.model_validate(state["route_decisions"][-1])
        return "rewrite" if decision.next_action == RouteAction.REWRITE else "finish"

    @staticmethod
    def _rewrite_edge(state: PipelineState) -> str:
        decision = RouteDecision.model_validate(state["route_decisions"][-1])
        return "rewrite_ok" if decision.next_action == RouteAction.REWRITE else "rewrite_failed"

    def _project_result(self, state: PipelineState) -> PipelineResult:
        versions = self._versions(state)
        selections = [
            VersionSelection.model_validate(item)
            for item in state.get("version_selections", [])
        ]
        best_id = selections[-1].selected_version_id if selections else (
            versions[0].version_id if versions else ""
        )
        last_id = state.get("current_version_id", "") if versions else ""
        stop_raw = state.get("stop_reason")
        return PipelineResult(
            run_id=state["run_id"],
            task_id=self._task(state).task_id,
            task_mode=self._task(state).mode,
            experiment_id=self._config(state).experiment_id,
            method_id=self._config(state).method_id,
            status=RunStatus(state.get("status", RunStatus.FAILED.value)),
            stop_reason=StopReason(stop_raw) if stop_raw else None,
            best_version_id=best_id,
            last_version_id=last_id,
            design_blueprint=(
                LessonDesignBlueprint.model_validate(state["design_blueprint"])
                if state.get("design_blueprint")
                else None
            ),
            versions=versions,
            critiques=self._critique_history(state),
            validation_batches=[
                ValidationBatch.model_validate(item)
                for item in state.get("validation_batches", [])
            ],
            rewrite_records=[
                RewriteRecord.model_validate(item)
                for item in state.get("rewrite_records", [])
            ],
            route_decisions=[
                RouteDecision.model_validate(item)
                for item in state.get("route_decisions", [])
            ],
            version_selections=selections,
            iterations=[
                IterationRecord.model_validate(item)
                for item in state.get("iterations", [])
            ],
            optimization_quality_gate=state.get("optimization_quality_gate"),
            optimization_comparison=state.get("optimization_comparison"),
            model_call_count=state.get("model_call_count", 0),
            token_usage=TokenUsage.model_validate(
                state.get("token_usage", TokenUsage().model_dump(mode="json"))
            ),
            estimated_cost=state.get("estimated_cost", 0.0),
            trace_path=state.get("trace_path", ""),
            errors=state.get("errors", []),
        )

    def _trace(self, state: PipelineState) -> TraceStore:
        return self._traces[state["run_id"]]

    @staticmethod
    def _task(state: PipelineState) -> LessonTask:
        return LessonTask.model_validate(state["task"])

    @staticmethod
    def _config(state: PipelineState) -> ExperimentConfig:
        return ExperimentConfig.model_validate(state["config"])

    @staticmethod
    def _effective_config(task: LessonTask, config: ExperimentConfig) -> ExperimentConfig:
        """Keep generation's budget unchanged while giving revision its own cap."""

        if task.mode != TaskMode.OPTIMIZE:
            return config
        payload = config.model_dump(mode="python")
        if config.optimization_max_model_calls is not None:
            payload["max_model_calls"] = config.optimization_max_model_calls
        if config.optimization_max_total_tokens is not None:
            payload["max_total_tokens"] = config.optimization_max_total_tokens
        return ExperimentConfig.model_validate(payload)

    @staticmethod
    def _versions(state: PipelineState) -> list[LessonPlanVersion]:
        return [LessonPlanVersion.model_validate(item) for item in state.get("versions", [])]

    def _current_version(self, state: PipelineState) -> LessonPlanVersion:
        return self._version_by_id(state, state["current_version_id"])

    def _version_by_id(self, state: PipelineState, version_id: str) -> LessonPlanVersion:
        return next(item for item in self._versions(state) if item.version_id == version_id)

    @staticmethod
    def _critique_history(state: PipelineState) -> list[CritiqueItem]:
        return [
            CritiqueItem.model_validate(item)
            for item in state.get("critique_history", [])
        ]

    @staticmethod
    def _current_batch(state: PipelineState) -> CritiqueBatch:
        raw = state.get("current_critique_batch")
        if raw is None:
            raise ValueError("current critique batch is missing")
        return CritiqueBatch.model_validate(raw)

    @staticmethod
    def _usage(state: PipelineState) -> TokenUsage:
        return TokenUsage.model_validate(state["token_usage"])

    @staticmethod
    def _sum_usage(left: TokenUsage, right: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=left.input_tokens + right.input_tokens,
            output_tokens=left.output_tokens + right.output_tokens,
        )

    @staticmethod
    def _attempt_count(output: AgentOutput) -> int:
        return output.metadata.attempts if output.metadata else 1

    @staticmethod
    def _worst_case_attempts(
        config: ExperimentConfig,
        profile_ids: list[str],
    ) -> int:
        """Reserve every configured retry so max_model_calls is a hard boundary."""

        return sum(
            config.role_model_configs[profile_id].max_retries + 1
            for profile_id in profile_ids
        )

    @staticmethod
    def _call_metadata(output: AgentOutput) -> dict[str, object] | None:
        return asdict(output.metadata) if output.metadata else None

    def _aware_now(self) -> datetime:
        value = self._clock()
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    def _elapsed_seconds(self, state: PipelineState) -> float:
        return self._elapsed_from_iso(state["started_at"])

    def _elapsed_from_iso(self, raw: str) -> float:
        started = datetime.fromisoformat(raw)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return max(0.0, (self._aware_now() - started).total_seconds())
