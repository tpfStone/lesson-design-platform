"""Offline finalization contracts for the distinct optimization delivery path."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from support import make_config, make_document, make_task, make_version

from paper4_pipeline.agents.optimization_compare import PairwiseComparison
from paper4_pipeline.agents.protocols import AgentCallMetadata, AgentOutput
from paper4_pipeline.control.versioning import select_best_version
from paper4_pipeline.domain.models import (
    RouteAction, RouteDecision, RunStatus, StopReason, TaskMode, TokenUsage,
)
from paper4_pipeline.observability.trace import TraceStore
from paper4_pipeline.orchestration.graph import Paper4Workflow
from test_graph_integration import _Rewriter, _suite


class _ComparingJudge:
    profile_id = "judge_v0_1"

    def __init__(self, verdict: str) -> None:
        self.verdict = verdict
        self.calls = 0

    def compare_optimization(self, task, baseline, candidate):
        self.calls += 1
        return AgentOutput(
            value=PairwiseComparison(
                baseline_version_id=baseline.version_id,
                candidate_version_id=candidate.version_id,
                verdict=self.verdict,
                target_issue_progress=(
                    "improved" if self.verdict == "candidate_preferred" else "worse"
                ),
                changed_sections=["assessment_plan"],
                reason="Two order-balanced offline fixture votes.",
            ),
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            estimated_cost=0.01,
            metadata=AgentCallMetadata(
                provider="offline-fixture", model_name="fixture",
                prompt_id="pairwise-fixture", prompt_version="1",
                prompt_sha256="fixture", attempts=2,
            ),
        )


class OptimizationFinalizeTests(unittest.TestCase):
    def test_optimization_budget_does_not_raise_generation_cap(self):
        config = make_config(
            max_model_calls=42, max_total_tokens=360000,
            optimization_max_model_calls=60,
            optimization_max_total_tokens=720000,
        )
        source = make_task()
        optimize = source.model_copy(update={
            "mode": TaskMode.OPTIMIZE,
            "initial_plan": make_document(source, high_quality=True),
        })
        self.assertIs(config, Paper4Workflow._effective_config(source, config))
        effective = Paper4Workflow._effective_config(optimize, config)
        self.assertEqual((60, 720000), (
            effective.max_model_calls, effective.max_total_tokens,
        ))
        self.assertEqual((42, 360000), (
            config.max_model_calls, config.max_total_tokens,
        ))

    def _run(self, *, baseline_score, candidate_score, verdict, reason):
        source = make_task()
        task = source.model_copy(update={
            "mode": TaskMode.OPTIMIZE,
            "initial_plan": make_document(source, high_quality=True),
        })
        config = make_config(max_model_calls=60, max_total_tokens=720000)
        baseline = make_version("v0", 0, score=baseline_score, task=task)
        edited = baseline.document.model_copy(deep=True)
        edited.assessment_plan += " 增加学生出口题并依据回答调整支架。"
        candidate = make_version(
            "v1", 1, score=candidate_score, task=task, document=edited,
            parent_version_id="v0", change_count=1,
        )
        selection = select_best_version(
            [baseline, candidate], config,
            dedupe_equivalent_content=True, task_mode=TaskMode.OPTIMIZE,
        )
        self.assertEqual("v1", selection.selected_version_id)
        judge = _ComparingJudge(verdict)
        suite = _suite(config, _Rewriter())
        object.__setattr__(suite, "judge", judge)
        with tempfile.TemporaryDirectory() as directory:
            workflow = Paper4Workflow(suite, Path(directory))
            workflow._traces["opt-finalize"] = TraceStore(
                Path(directory) / "opt-finalize", "opt-finalize", task.task_id,
            )
            state = {
                "run_id": "opt-finalize",
                "task": task.model_dump(mode="json"),
                "config": config.model_dump(mode="json"),
                "versions": [baseline.model_dump(mode="json"), candidate.model_dump(mode="json")],
                "current_version_id": candidate.version_id,
                "version_selections": [selection.model_dump(mode="json")],
                "route_decisions": [RouteDecision(
                    decision_id="final-route", next_action=RouteAction.FINALIZE,
                    primary_reason=reason, triggered_reasons=[reason],
                ).model_dump(mode="json")],
                "model_call_count": 12,
                "token_usage": TokenUsage(input_tokens=1000, output_tokens=500).model_dump(mode="json"),
                "estimated_cost": 0.1,
                "status": RunStatus.RUNNING.value,
                "trace_path": str(workflow._traces["opt-finalize"].path),
            }
            updates = workflow._finalize(state)
            result = workflow._project_result({**state, **updates})
        return result, judge

    def test_flat_score_keeps_real_edit_as_review_candidate(self):
        result, judge = self._run(
            baseline_score=7.7, candidate_score=7.7,
            verdict="candidate_preferred", reason=StopReason.MAX_ROUNDS,
        )
        self.assertEqual(1, judge.calls)
        self.assertEqual("v1", result.best_version_id)
        self.assertEqual(RunStatus.NEEDS_HUMAN, result.status)
        self.assertFalse(result.optimization_quality_gate["passed"])
        self.assertEqual("candidate_preferred", result.optimization_comparison["verdict"])
        self.assertEqual(14, result.model_call_count)
        self.assertEqual(1650, result.token_usage.total_tokens)

    def test_quality_gate_and_pairwise_agreement_can_complete(self):
        result, _ = self._run(
            baseline_score=7.8, candidate_score=8.1,
            verdict="candidate_preferred", reason=StopReason.QUALITY_PASSED,
        )
        self.assertEqual(RunStatus.COMPLETED, result.status)
        self.assertEqual("v1", result.best_version_id)
        self.assertTrue(result.optimization_quality_gate["passed"])
        self.assertFalse(result.version_selections[-1].requires_human)

    def test_pairwise_rejection_retains_baseline_and_candidate(self):
        result, _ = self._run(
            baseline_score=7.7, candidate_score=7.7,
            verdict="baseline_preferred", reason=StopReason.MAX_ROUNDS,
        )
        self.assertEqual("v0", result.best_version_id)
        self.assertEqual("v1", result.last_version_id)
        self.assertEqual(RunStatus.NEEDS_HUMAN, result.status)
        self.assertFalse(result.optimization_quality_gate["passed"])


if __name__ == "__main__":
    unittest.main()
