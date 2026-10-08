from __future__ import annotations

import unittest

from support import (
    REPO_ROOT,
    make_config,
    make_critique,
    make_evaluation,
    make_task,
    make_version,
)

from paper4_pipeline.adapters.paper3 import simulation_report_to_critiques
from paper4_pipeline.adapters.tutorial34 import load_tutorial34_tasks
from paper4_pipeline.control.lifecycle import transition_critique
from paper4_pipeline.control.routing import route_after_evaluation
from paper4_pipeline.control.versioning import select_best_version
from paper4_pipeline.domain.models import (
    CritiqueSource,
    CritiqueStatus,
    RouteAction,
    RubricDimension,
    Severity,
    SimulationEvent,
    SimulationIssue,
    SimulationReport,
    StopReason,
    TokenUsage,
)


class DeterministicRoutingTests(unittest.TestCase):
    def test_optimization_baseline_must_be_reviewed_even_if_score_passes(self) -> None:
        config = make_config(quality_threshold=8.0, critical_dimension_floor=7.0)
        version = make_version("v0", 0, score=8.5)
        decision = route_after_evaluation(
            report=version.internal_evaluation,
            rule_report=version.rule_check_report,
            versions=[version], config=config, model_call_count=2,
            token_usage=TokenUsage(input_tokens=100, output_tokens=100),
            estimated_cost=0.0, score_deltas=[], required_next_model_calls=5,
            require_initial_review=True,
        )
        self.assertEqual(RouteAction.CONTINUE_REVIEW, decision.next_action)
        self.assertNotIn(StopReason.QUALITY_PASSED, decision.triggered_reasons)

    def test_quality_gate_finalizes_with_quality_passed(self) -> None:
        config = make_config(quality_threshold=8.0, critical_dimension_floor=7.0)
        version = make_version("v0", 0, score=8.5)

        decision = route_after_evaluation(
            report=version.internal_evaluation,
            rule_report=version.rule_check_report,
            versions=[version],
            config=config,
            model_call_count=2,
            token_usage=TokenUsage(input_tokens=100, output_tokens=100),
            estimated_cost=0.0,
            score_deltas=[],
            required_next_model_calls=5,
        )

        self.assertEqual(RouteAction.FINALIZE, decision.next_action)
        self.assertEqual(StopReason.QUALITY_PASSED, decision.primary_reason)

    def test_max_rounds_is_enforced_at_exact_boundary(self) -> None:
        config = make_config(max_rounds=0)
        version = make_version("v0", 0, score=6.0)

        decision = route_after_evaluation(
            report=version.internal_evaluation,
            rule_report=version.rule_check_report,
            versions=[version],
            config=config,
            model_call_count=0,
            token_usage=TokenUsage(),
            estimated_cost=0.0,
            score_deltas=[],
            required_next_model_calls=1,
        )

        self.assertEqual(RouteAction.FINALIZE, decision.next_action)
        self.assertEqual(StopReason.MAX_ROUNDS, decision.primary_reason)

    def test_max_rounds_does_not_report_unused_future_retry_reserve_as_budget(
        self,
    ) -> None:
        config = make_config(
            max_rounds=2,
            max_model_calls=30,
            max_total_tokens=240_000,
            max_estimated_cost=5.0,
        )
        version = make_version("v2", 2, score=7.25)

        decision = route_after_evaluation(
            report=version.internal_evaluation,
            rule_report=version.rule_check_report,
            versions=[version],
            config=config,
            model_call_count=15,
            token_usage=TokenUsage(input_tokens=180_000, output_tokens=22_000),
            estimated_cost=0.135,
            score_deltas=[],
            required_next_model_calls=18,
        )

        self.assertEqual(RouteAction.FINALIZE, decision.next_action)
        self.assertEqual(StopReason.MAX_ROUNDS, decision.primary_reason)
        self.assertEqual([StopReason.MAX_ROUNDS], decision.triggered_reasons)

    def test_actual_budget_limit_remains_visible_when_max_rounds_is_also_hit(
        self,
    ) -> None:
        config = make_config(max_rounds=2, max_model_calls=30)
        version = make_version("v2", 2, score=7.25)

        decision = route_after_evaluation(
            report=version.internal_evaluation,
            rule_report=version.rule_check_report,
            versions=[version],
            config=config,
            model_call_count=30,
            token_usage=TokenUsage(),
            estimated_cost=0.0,
            score_deltas=[],
            required_next_model_calls=18,
        )

        self.assertEqual(RouteAction.FINALIZE, decision.next_action)
        self.assertEqual(StopReason.BUDGET_EXCEEDED, decision.primary_reason)
        self.assertEqual(
            [StopReason.BUDGET_EXCEEDED, StopReason.MAX_ROUNDS],
            decision.triggered_reasons,
        )

    def test_projected_model_calls_cannot_exceed_budget(self) -> None:
        config = make_config(max_model_calls=3)
        version = make_version("v0", 0, score=6.0)

        decision = route_after_evaluation(
            report=version.internal_evaluation,
            rule_report=version.rule_check_report,
            versions=[version],
            config=config,
            model_call_count=2,
            token_usage=TokenUsage(),
            estimated_cost=0.0,
            score_deltas=[],
            required_next_model_calls=2,
        )

        self.assertEqual(RouteAction.FINALIZE, decision.next_action)
        self.assertEqual(StopReason.BUDGET_EXCEEDED, decision.primary_reason)

    def test_projected_model_calls_equal_to_budget_are_allowed(self) -> None:
        config = make_config(max_model_calls=3)
        version = make_version("v0", 0, score=6.0)

        decision = route_after_evaluation(
            report=version.internal_evaluation,
            rule_report=version.rule_check_report,
            versions=[version],
            config=config,
            model_call_count=2,
            token_usage=TokenUsage(),
            estimated_cost=0.0,
            score_deltas=[],
            required_next_model_calls=1,
        )

        self.assertEqual(RouteAction.CONTINUE_REVIEW, decision.next_action)
        self.assertIsNone(decision.primary_reason)

    def test_regression_guard_requests_rollback(self) -> None:
        config = make_config()
        version = make_version("v0", 0, score=6.0)
        report = make_evaluation(
            "v0", score=6.0, regressions=["critique-reappeared"]
        )

        decision = route_after_evaluation(
            report=report,
            rule_report=version.rule_check_report,
            versions=[version],
            config=config,
            model_call_count=0,
            token_usage=TokenUsage(),
            estimated_cost=0.0,
            score_deltas=[],
            required_next_model_calls=1,
        )

        self.assertEqual(RouteAction.ROLLBACK, decision.next_action)
        self.assertEqual(StopReason.REGRESSION_GUARD, decision.primary_reason)


class BestVersionTests(unittest.TestCase):
    def test_optimization_near_tie_requires_human_even_with_different_open_counts(self) -> None:
        task = make_task()
        v0 = make_version("v0", 0, score=8.1, task=task, unresolved_issue_count=0)
        v1 = make_version("v1", 1, score=8.2, task=task,
                          parent_version_id="v0", unresolved_issue_count=1)
        document = v1.document.model_copy(update={
            "content_analysis": v1.document.content_analysis + " 添加一份可核验材料。"
        })
        v1 = v1.model_copy(update={"document": document})
        selection = select_best_version(
            [v0, v1], make_config(epsilon=0.11), dedupe_equivalent_content=True,
        )
        self.assertTrue(selection.requires_human)

    def test_optimization_does_not_promote_same_content_for_score_noise(self) -> None:
        task = make_task()
        v0 = make_version("v0", 0, score=8.1, task=task)
        v1 = make_version("v1", 1, score=8.2, task=task, parent_version_id="v0")
        selection = select_best_version(
            [v0, v1], make_config(), dedupe_equivalent_content=True,
        )
        self.assertEqual("v0", selection.selected_version_id)
        self.assertIn("equivalent_content_re_evaluation", selection.eliminated_candidates["v1"])

    def test_best_version_can_be_earlier_than_last_version(self) -> None:
        task = make_task()
        v0 = make_version("v0", 0, score=9.0, task=task)
        v1 = make_version(
            "v1",
            1,
            score=7.0,
            task=task,
            parent_version_id="v0",
            change_count=3,
        )

        selection = select_best_version([v0, v1], make_config())

        self.assertEqual("v0", selection.selected_version_id)
        self.assertNotEqual("v1", selection.selected_version_id)

    def test_higher_quality_version_wins_over_raw_draft_despite_open_items(
        self,
    ) -> None:
        # Regression guard for the Pythagorean demo run: v1 scored 8.375 but
        # carried two open (non-high-risk) items, while raw v0 scored 7.938
        # with none.  The old rank compared unresolved_issue_count *before* the
        # scores, so the unimproved draft was exported as "best".  Quality must
        # be the primary signal among safe candidates.
        task = make_task()
        v0 = make_version("v0", 0, score=7.938, task=task, change_count=0)
        v1 = make_version(
            "v1",
            1,
            score=8.375,
            task=task,
            parent_version_id="v0",
            change_count=13,
            unresolved_issue_count=2,
        )

        selection = select_best_version([v0, v1], make_config())

        self.assertEqual("v1", selection.selected_version_id)
        self.assertEqual(["v1", "v0"], selection.eligible_candidate_ids)

    def test_equal_quality_prefers_cleaner_version(self) -> None:
        task = make_task()
        clean = make_version("v0", 0, score=8.0, task=task, change_count=0)
        open_version = make_version(
            "v1",
            1,
            score=8.0,
            task=task,
            parent_version_id="v0",
            change_count=5,
            unresolved_issue_count=3,
        )

        selection = select_best_version([clean, open_version], make_config())

        self.assertEqual("v0", selection.selected_version_id)


class Paper3AdapterTests(unittest.TestCase):
    def test_timing_issue_becomes_traceable_feasibility_critique(self) -> None:
        report = SimulationReport(
            simulation_id="sim-001",
            lesson_plan_version_id="v1",
            lesson_plan_hash="12345678",
            events=[
                SimulationEvent(
                    event_id="event-1",
                    step_id="step-2",
                    minute_start=10,
                    minute_end=30,
                    role="student",
                    observation="讨论在规定时间后仍未完成。",
                )
            ],
            issues=[
                SimulationIssue(
                    issue_id="issue-1",
                    type="timing",
                    severity=Severity.HIGH,
                    procedure_step_id="step-2",
                    evidence_event_ids=["event-1"],
                    description="探究环节预计超时。",
                    suggestion="减少子任务数量并保留核心讨论。",
                )
            ],
        )

        batch = simulation_report_to_critiques(report, round_index=2)

        self.assertEqual("v1", batch.plan_version_id)
        self.assertEqual(2, batch.round_index)
        self.assertEqual(1, len(batch.items))
        critique = batch.items[0]
        self.assertEqual(CritiqueSource.SIMULATION, critique.source)
        self.assertEqual(RubricDimension.CLASSROOM_FEASIBILITY, critique.dimension)
        self.assertEqual("/procedure_steps/step-2", critique.target_path)
        self.assertIn("event-1", critique.evidence)
        self.assertEqual(["simulation:sim-001"], critique.knowledge_source_refs)


class Tutorial34AdapterTests(unittest.TestCase):
    def test_existing_tutorial34_dev_set_loads_without_legacy_runtime(self) -> None:
        path = REPO_ROOT / "data" / "tutorial34_v0_1" / "tasks" / "dev.jsonl"

        tasks = load_tutorial34_tasks(path)

        self.assertEqual(10, len(tasks))
        first = tasks[0]
        self.assertEqual("math_pythagorean_zh", first.task_id)
        self.assertEqual("generate", first.mode.value)
        self.assertEqual(
            [
                "student_analysis",
                "learning_objectives",
                "key_points",
                "difficult_points",
                "procedure_steps",
                "assessment_plan",
                "homework",
            ],
            first.required_sections,
        )
        self.assertEqual(
            "tutorial34-v0.1-to-paper4-task-v0.1",
            first.metadata["migration_adapter"],
        )


if __name__ == "__main__":
    unittest.main()
