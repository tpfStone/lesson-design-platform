"""Offline contract tests for optimization-specific routing and delivery.

These fixtures are deliberately not presented as real model runs. They pin
policy decisions that previously let score noise choose an unchanged v0.
"""

from __future__ import annotations

import unittest

from support import make_config, make_task, make_version

from paper4_pipeline.control.optimization import optimization_quality_gate
from paper4_pipeline.control.routing import route_after_evaluation
from paper4_pipeline.control.versioning import select_best_version
from paper4_pipeline.domain.models import RouteAction, StopReason, TaskMode, TokenUsage


def _revision(version_id: str, iteration: int, score: float, *, task=None,
              parent_version_id: str = "v0", text: str = "补充可观察的学生作品。"):
    version = make_version(
        version_id, iteration, score=score, task=task,
        parent_version_id=parent_version_id, change_count=1,
        unresolved_issue_count=iteration * 5,
    )
    document = version.document.model_copy(deep=True)
    document.content_analysis += text
    return version.model_copy(update={"document": document})


def _route(versions, config, *, score_deltas=None, model_calls=8):
    latest = versions[-1]
    return route_after_evaluation(
        report=latest.internal_evaluation,
        rule_report=latest.rule_check_report,
        versions=versions,
        config=config,
        model_call_count=model_calls,
        token_usage=TokenUsage(input_tokens=1000, output_tokens=500),
        estimated_cost=0.01,
        score_deltas=score_deltas or [],
        required_next_model_calls=4,
        task_mode=TaskMode.OPTIMIZE,
    )


class OptimizationQualityGateTests(unittest.TestCase):
    def test_same_content_higher_score_is_not_an_optimization(self):
        task = make_task()
        baseline = make_version("v0", 0, score=8.1, task=task)
        rescored = make_version("v1", 1, score=8.6, task=task,
                                parent_version_id="v0", change_count=1)
        gate = optimization_quality_gate(baseline, rescored, make_config())
        self.assertFalse(gate["content_changed"])
        self.assertFalse(gate["passed"])

    def test_absolute_score_alone_does_not_satisfy_gain_requirement(self):
        task = make_task()
        baseline = make_version("v0", 0, score=8.1, task=task)
        candidate = _revision("v1", 1, 8.2, task=task)
        gate = optimization_quality_gate(
            baseline, candidate, make_config(optimization_min_score_gain=0.2),
        )
        self.assertTrue(gate["content_changed"])
        self.assertTrue(gate["absolute_target_met"])
        self.assertFalse(gate["relative_target_met"])
        self.assertFalse(gate["passed"])

    def test_real_safe_revision_meets_internal_threshold_only(self):
        task = make_task()
        baseline = make_version("v0", 0, score=7.8, task=task)
        candidate = _revision("v1", 1, 8.1, task=task)
        gate = optimization_quality_gate(baseline, candidate, make_config())
        self.assertTrue(gate["passed"])
        self.assertIn("不能替代教师判断", gate["note"])


class OptimizationRoutingTests(unittest.TestCase):
    def test_baseline_cannot_pass_optimization_threshold_without_revision(self):
        baseline = make_version("v0", 0, score=9.0)
        decision = _route([baseline], make_config())
        self.assertEqual(RouteAction.CONTINUE_REVIEW, decision.next_action)
        self.assertNotIn(StopReason.QUALITY_PASSED, decision.triggered_reasons)

    def test_flat_judge_scores_do_not_trigger_plateau_during_optimization(self):
        task = make_task()
        baseline = make_version("v0", 0, score=7.7, task=task)
        first = _revision("v1", 1, 7.7, task=task)
        second = _revision("v2", 2, 7.7, task=task,
                           parent_version_id="v1", text="新增针对误概念的出口题。")
        decision = _route([baseline, first, second], make_config(
            optimization_max_rounds=3, max_rounds=2,
        ), score_deltas=[0.0, 0.0])
        self.assertEqual(RouteAction.CONTINUE_REVIEW, decision.next_action)
        self.assertNotIn(StopReason.PLATEAU, decision.triggered_reasons)

    def test_third_rewrite_is_the_optimization_limit(self):
        task = make_task()
        baseline = make_version("v0", 0, score=7.7, task=task)
        third = _revision("v3", 3, 7.7, task=task)
        decision = _route([baseline, third], make_config(
            optimization_max_rounds=3, max_rounds=5,
        ), score_deltas=[0.0, 0.0, 0.0])
        self.assertEqual(RouteAction.FINALIZE, decision.next_action)
        self.assertEqual(StopReason.MAX_ROUNDS, decision.primary_reason)
        self.assertNotIn(StopReason.PLATEAU, decision.triggered_reasons)


class OptimizationSelectionTests(unittest.TestCase):
    def test_tied_safe_revision_is_delivered_as_provisional_not_original(self):
        task = make_task()
        baseline = make_version("v0", 0, score=7.7, task=task)
        first = _revision("v1", 1, 7.7, task=task)
        second = _revision("v2", 2, 7.7, task=task, parent_version_id="v1",
                           text="新增针对误概念的出口题。")
        selection = select_best_version(
            [baseline, first, second], make_config(),
            dedupe_equivalent_content=True, task_mode=TaskMode.OPTIMIZE,
        )
        self.assertEqual("v2", selection.selected_version_id)
        self.assertTrue(selection.requires_human)
        self.assertIn("待教师复核稿", selection.selection_reason)

    def test_material_score_regression_does_not_promote_revision(self):
        task = make_task()
        baseline = make_version("v0", 0, score=8.2, task=task)
        regression = _revision("v1", 1, 7.0, task=task)
        selection = select_best_version(
            [baseline, regression], make_config(),
            dedupe_equivalent_content=True, task_mode=TaskMode.OPTIMIZE,
        )
        self.assertEqual("v0", selection.selected_version_id)


if __name__ == "__main__":
    unittest.main()
