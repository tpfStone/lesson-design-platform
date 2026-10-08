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


class RevisionNodes:
    def _rewriter(self, state: PipelineState) -> PipelineState:
        started = perf_counter()
        task = self._task(state)
        config = self._config(state)
        current = self._current_version(state)
        batch = self._current_batch(state)
        accepted = actionable_critiques(batch)
        profile = self._profiles[config.rewriter_profile_id]
        knowledge = build_knowledge_bundle(profile, task)
        try:
            output = self.agents.rewriter.rewrite(
                task,
                current,
                accepted,
                batch.round_index,
                knowledge,
            )
        except Exception as exc:
            # A rewrite is the only step that turns a reviewed draft into the
            # next version.  If the real model cannot produce a contract-valid
            # full-document rewrite after its capped retries, that must not
            # discard the whole run: mark the accepted critiques unresolved,
            # record the failure, and finish on the last safe version.
            return self._abort_rewrite(
                state,
                task=task,
                current=current,
                batch=batch,
                accepted=accepted,
                exc=exc,
                started=started,
                profile=profile,
                knowledge=knowledge,
            )
        new_version_id = f"v{batch.round_index}"
        rule_report = check_lesson_plan(
            output.value.document,
            task,
            config.duration_tolerance_minutes,
            report_id=f"rule-{new_version_id}",
        )
        updated_batch = apply_rewrite_outcome(
            batch,
            output.value,
            batch.round_index,
            new_version_id,
        )
        history = merge_critique_history(self._critique_history(state), updated_batch)
        rewrite_record = RewriteRecord(
            rewrite_id=stable_id("rewrite", current.version_id, new_version_id),
            input_version_id=current.version_id,
            output_version_id=new_version_id,
            strategy=(
                "targeted_patch" if output.metadata and
                output.metadata.prompt_id == "rewrite_patch_prompt"
                else "full_document" if output.metadata else "legacy_unknown"
            ),
            accepted_critique_ids=[item.critique_id for item in accepted],
            changes=output.value.changes,
            unresolved_critique_ids=output.value.unresolved_critique_ids,
            unresolved_reasons=output.value.unresolved_reasons,
        )
        usage = self._sum_usage(self._usage(state), output.usage)
        total_cost = state["estimated_cost"] + output.estimated_cost
        new_version = LessonPlanVersion(
            version_id=new_version_id,
            parent_version_id=current.version_id,
            iteration=batch.round_index,
            document=output.value.document,
            created_by_profile_id=self.agents.rewriter.profile_id,
            created_at=self._aware_now(),
            document_hash=document_hash(output.value.document),
            addressed_critique_ids=[
                item.critique_id
                for item in updated_batch.items
                if item.status
                in {
                    CritiqueStatus.IMPLEMENTED,
                    CritiqueStatus.PARTIALLY_IMPLEMENTED,
                }
            ],
            unresolved_critique_ids=list(output.value.unresolved_critique_ids),
            diff_summary=f"按 {len(output.value.changes)} 条已验证意见做局部修改",
            rule_check_report=rule_report,
            change_count=len(output.value.changes),
            estimated_cost=total_cost,
        )
        validation = ValidationBatch.model_validate(state["validation_batches"][-1])
        cycle = state.get("cycle_start") or {
            "started_at": self._aware_now().isoformat(),
            "token_usage": state["token_usage"],
            "cost": state["estimated_cost"],
        }
        pending = {
            "iteration_id": stable_id("iteration", state["run_id"], batch.round_index),
            "input_version_id": current.version_id,
            "output_version_id": new_version_id,
            "critique_ids": [item.critique_id for item in batch.items],
            "validation_decision_ids": [
                item.decision_id for item in validation.decisions
            ],
            "rewrite_id": rewrite_record.rewrite_id,
            "started_at": cycle["started_at"],
            "start_token_usage": cycle["token_usage"],
            "start_cost": cycle["cost"],
        }
        self._trace(state).append(
            event_type="rewrite_completed",
            stage="rewriter",
            actor_profile_id=self.agents.rewriter.profile_id,
            knowledge_bundle_id=knowledge.bundle_id,
            round_index=batch.round_index,
            version_id=new_version_id,
            input_summary={
                "input_version_id": current.version_id,
                "accepted_critiques": [
                    item.model_dump(mode="json") for item in accepted
                ],
                "agent_profile": profile.model_dump(mode="json"),
                "knowledge_bundle": knowledge.model_dump(mode="json"),
            },
            output_summary={
                "rewrite_outcome": output.value.model_dump(mode="json"),
                "rewrite_record": rewrite_record.model_dump(mode="json"),
                "rule_report": rule_report.model_dump(mode="json"),
                "document_hash": new_version.document_hash,
                "model_call": self._call_metadata(output),
            },
            token_usage=output.usage,
            estimated_cost=output.estimated_cost,
            duration_seconds=perf_counter() - started,
        )
        return {
            "versions": [
                *state["versions"],
                new_version.model_dump(mode="json"),
            ],
            "current_version_id": new_version_id,
            "current_critique_batch": updated_batch.model_dump(mode="json"),
            "critique_history": [item.model_dump(mode="json") for item in history],
            "rewrite_records": [
                *state["rewrite_records"],
                rewrite_record.model_dump(mode="json"),
            ],
            "model_call_count": state["model_call_count"]
            + self._attempt_count(output),
            "token_usage": usage.model_dump(mode="json"),
            "estimated_cost": total_cost,
            "pending_iteration": pending,
            "knowledge_bundles": [
                *state["knowledge_bundles"],
                knowledge.model_dump(mode="json"),
            ],
        }


    def _abort_rewrite(
        self,
        state: PipelineState,
        *,
        task: LessonTask,
        current: LessonPlanVersion,
        batch: CritiqueBatch,
        accepted: list[CritiqueItem],
        exc: Exception,
        started: float,
        profile: AgentProfile,
        knowledge: KnowledgeBundle,
    ) -> PipelineState:
        """Turn a failed rewrite into a recorded, reviewable stop.

        Accepted critiques are transitioned to UNRESOLVED so the ledger never
        claims an implemented fix that does not exist, the failure is preserved
        in ``errors`` and the trace, and routing finishes on the best
        already-reviewed version.  A usable prior version means this is a
        NEEDS_HUMAN outcome, not a total pipeline failure: no unverified edit
        is accepted, while the successfully generated draft remains a normal
        deliverable for manual review.
        """
        message = f"{type(exc).__name__}: {exc}"
        failed_attempts = int(getattr(exc, "attempts", 1))
        failed_usage = getattr(exc, "usage", TokenUsage())
        if not isinstance(failed_usage, TokenUsage):
            failed_usage = TokenUsage()
        failed_cost = float(getattr(exc, "estimated_cost", 0.0))
        usage = self._sum_usage(self._usage(state), failed_usage)
        cost = state["estimated_cost"] + failed_cost

        updated_items: list[CritiqueItem] = []
        for item in batch.items:
            if item.status == CritiqueStatus.ACCEPTED:
                item = transition_critique(
                    item,
                    CritiqueStatus.UNRESOLVED,
                    round_index=batch.round_index,
                    version_id=current.version_id,
                    note="rewriter failed; accepted critique was not implemented",
                )
            updated_items.append(item)
        updated_batch_payload = batch.model_dump(mode="python")
        updated_batch_payload["items"] = updated_items
        updated_batch = CritiqueBatch.model_validate(updated_batch_payload)
        history = merge_critique_history(self._critique_history(state), updated_batch)
        if not accepted:
            # Nothing was accepted, so this is effectively a validation_router
            # stop rather than a failed rewrite attempt.
            decision = RouteDecision(
                decision_id=f"route-rewrite-empty-{batch.round_index}",
                next_action=RouteAction.FINALIZE,
                primary_reason=StopReason.NO_ACTIONABLE_FEEDBACK,
                triggered_reasons=[],
                explanation="没有可执行的已接受意见，无法进入改写。",
            )
        else:
            decision = RouteDecision(
                decision_id=f"route-rewrite-abort-{batch.round_index}",
                next_action=RouteAction.HUMAN_REVIEW,
                primary_reason=StopReason.REWRITE_FAILED,
                triggered_reasons=[StopReason.REWRITE_FAILED],
                explanation=(
                    "改写多次尝试仍无法产出满足契约的新版本；已将本轮接受意见"
                    "标为未解决，保留上一个安全版本并转人工复核。"
                ),
            )
        self._trace(state).append(
            event_type="rewrite_aborted",
            stage="rewriter",
            actor_profile_id=self.agents.rewriter.profile_id,
            knowledge_bundle_id=knowledge.bundle_id,
            round_index=batch.round_index,
            version_id=current.version_id,
            error=message,
            input_summary={
                "accepted_critique_ids": [
                    item.critique_id for item in accepted
                ],
                "agent_profile": profile.model_dump(mode="json"),
                "knowledge_bundle": knowledge.model_dump(mode="json"),
            },
            output_summary={
                "decision": decision.model_dump(mode="json"),
                "critique_statuses": {
                    item.critique_id: item.status.value for item in history
                },
            },
            token_usage=failed_usage,
            estimated_cost=failed_cost,
            duration_seconds=perf_counter() - started,
            status="error",
        )
        return {
            "current_critique_batch": updated_batch.model_dump(mode="json"),
            "critique_history": [item.model_dump(mode="json") for item in history],
            "route_decisions": [
                *state["route_decisions"],
                decision.model_dump(mode="json"),
            ],
            "stop_reason": decision.primary_reason.value,
            "pending_iteration": None,
            "model_call_count": state["model_call_count"] + failed_attempts,
            "token_usage": usage.model_dump(mode="json"),
            "estimated_cost": cost,
            "errors": [*state.get("errors", []), message],
        }


    def _verifier(self, state: PipelineState) -> PipelineState:
        current = self._current_version(state)
        batch = self._current_batch(state)
        verified_batch = verify_rewrite(
            batch,
            current.document,
            batch.round_index,
            current.version_id,
        )
        history = merge_critique_history(
            self._critique_history(state), verified_batch
        )
        history = detect_regressions(
            history,
            current.document,
            batch.round_index,
            current.version_id,
        )
        replacements = {item.critique_id: item for item in history}
        verified_payload = verified_batch.model_dump(mode="python")
        verified_payload["items"] = [
            replacements[item.critique_id] for item in verified_batch.items
        ]
        verified_batch = CritiqueBatch.model_validate(verified_payload)
        self._trace(state).append(
            event_type="rewrite_verified",
            stage="verifier",
            round_index=batch.round_index,
            version_id=current.version_id,
            input_summary={"rewrite_version_hash": current.document_hash},
            output_summary={
                "critique_statuses": {
                    item.critique_id: item.status.value for item in history
                }
            },
        )
        return {
            "current_critique_batch": verified_batch.model_dump(mode="json"),
            "critique_history": [item.model_dump(mode="json") for item in history],
        }

