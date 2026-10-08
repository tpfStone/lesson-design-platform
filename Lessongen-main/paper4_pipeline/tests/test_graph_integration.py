from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from support import make_config, make_document, make_evaluation, make_task

from paper4_pipeline.agents.profiles import default_profile_registry
from paper4_pipeline.agents.protocols import AgentCallMetadata, AgentOutput
from paper4_pipeline.agents.suite import AgentSuite
from paper4_pipeline.control.lifecycle import enforce_acceptance_cap
from paper4_pipeline.domain.models import (
    CritiqueBatch,
    CritiqueItem,
    CritiqueSource,
    CritiqueStatus,
    DesignCandidate,
    LessonDesignBlueprint,
    RewriteChange,
    RewriteOutcome,
    RouteAction,
    RubricDimension,
    RunStatus,
    StopReason,
    TaskMode,
    TokenUsage,
    ValidationBatch,
    ValidationDecision,
    ValidationDecisionKind,
)
from paper4_pipeline.orchestration.graph import Paper4Workflow


class _Designer:
    profile_id = "design_architect_v0_1"

    def design(self, task, knowledge=None):
        candidates = [
            DesignCandidate(
                candidate_id=f"candidate-{index}",
                title=f"证据路径{index}",
                design_thesis="用可比较证据推动概念形成",
                driving_question="什么证据可以支持这个结论？",
                learner_starting_point="学生会操作但解释不稳定",
                desired_conceptual_shift="从操作结果转向关系解释",
                learning_arc=["诊断", "比较", "解释"],
                pivotal_moment="学生用反例修正原解释",
                student_products=["证据卡"],
                concrete_materials=["可比较案例"],
                subject_specific_value="突出概念关系",
            )
            for index in (1, 2)
        ]
        return AgentOutput(
            LessonDesignBlueprint(
                blueprint_id="blueprint-test",
                task_id=task.task_id,
                candidates=candidates,
                selected_candidate_id="candidate-1",
                selection_reason="证据链更清楚",
                quality_non_negotiables=["必须留下可检查的学生证据"],
            )
        )


class _Writer:
    profile_id = "writer_v0_1"

    def generate(self, task, knowledge=None, blueprint=None):
        return AgentOutput(make_document(task, high_quality=True))


class _Critic:
    def __init__(self, profile_id, specs):
        self.profile_id = profile_id
        self.specs = specs

    def review(
        self,
        task,
        version,
        round_index,
        knowledge=None,
        prior_critiques=None,
    ):
        items = []
        if round_index == 1:
            for index, (dimension, target_path) in enumerate(self.specs, start=1):
                critique_id = f"{self.profile_id}-issue-{index}"
                items.append(
                    CritiqueItem(
                        critique_id=critique_id,
                        source=CritiqueSource.CRITIC,
                        critic_profile_id=self.profile_id,
                        dimension=dimension,
                        issue_code=f"integration_issue_{critique_id}",
                        target_path=target_path,
                        lesson_location=target_path,
                        issue="当前内容存在一个可执行的测试缺口。",
                        evidence="集成测试固定证据。",
                        actionable_suggestion="进行一项可核验修改。",
                        introduced_in_round=round_index,
                    )
                )
        return AgentOutput(
            CritiqueBatch(
                batch_id=f"batch-{self.profile_id}-{round_index}",
                plan_version_id=version.version_id,
                round_index=round_index,
                items=items,
            )
        )


class _CountedCritic(_Critic):
    def review(self, *args, **kwargs):
        output = super().review(*args, **kwargs)
        return AgentOutput(
            output.value,
            usage=TokenUsage(input_tokens=11, output_tokens=5),
            estimated_cost=0.2,
            metadata=AgentCallMetadata(
                provider="test",
                model_name="test",
                prompt_id="test",
                prompt_version="1",
                prompt_sha256="0" * 64,
                attempts=1,
            ),
        )


class _CountedFailingCritic:
    profile_id = "pedagogy_critic_v0_1"

    def review(self, *args, **kwargs):
        error = RuntimeError("counted critic failure")
        error.attempts = 2
        error.usage = TokenUsage(input_tokens=7, output_tokens=3)
        error.estimated_cost = 0.4
        raise error


class _Validator:
    profile_id = "validator_v0_1"

    def validate(self, task, version, critiques, round_index, knowledge=None):
        raw = [
            ValidationDecision(
                decision_id=f"decision-{round_index}-{index}",
                critique_id=item.critique_id,
                decision=ValidationDecisionKind.ACCEPT,
                grounded=True,
                relevant=True,
                actionable=True,
                conflict=False,
                priority=100 - index,
                reason="集成测试中意见仍适用于当前版本。",
            )
            for index, item in enumerate(critiques.items)
        ]
        decisions = enforce_acceptance_cap(raw)
        return AgentOutput(
            ValidationBatch(
                batch_id=f"validation-{round_index}",
                critique_batch_id=critiques.batch_id,
                round_index=round_index,
                decisions=decisions,
            )
        )


class _Judge:
    profile_id = "judge_v0_1"

    def evaluate(self, task, version, unresolved_issue_count, knowledge=None):
        return AgentOutput(
            make_evaluation(
                version.version_id,
                score=6.0 + version.iteration,
                unresolved_issue_count=unresolved_issue_count,
            )
        )


class _PassingJudge(_Judge):
    def evaluate(self, task, version, unresolved_issue_count, knowledge=None):
        return AgentOutput(make_evaluation(
            version.version_id, score=8.5,
            unresolved_issue_count=unresolved_issue_count,
        ))


class _Rewriter:
    profile_id = "rewriter_v0_1"

    def __init__(self, *, fail=False):
        self.fail = fail
        self.accepted_ids_by_round = []

    def rewrite(
        self,
        task,
        version,
        accepted_critiques,
        round_index,
        knowledge=None,
    ):
        self.accepted_ids_by_round.append(
            [item.critique_id for item in accepted_critiques]
        )
        if self.fail:
            raise RuntimeError("stubbed rewrite failure")
        document = version.document.model_copy(deep=True)
        document.assessment_plan = (
            document.assessment_plan + f" 第{round_index}轮补充证据。"
        )
        changes = [
            RewriteChange(
                critique_id=item.critique_id,
                target_path=item.target_path,
                lesson_location=item.lesson_location,
                before_summary="修改前内容",
                after_summary=f"第{round_index}轮已完成可核验修改",
                implementation_status="implemented",
            )
            for item in accepted_critiques
        ]
        return AgentOutput(RewriteOutcome(document=document, changes=changes))


def _suite(config, rewriter):
    profiles = default_profile_registry(config.role_model_configs)
    critics = [
        _Critic(
            "subject_critic_v0_1",
            [
                (RubricDimension.KNOWLEDGE_ACCURACY, "/content_analysis"),
                (RubricDimension.KNOWLEDGE_ACCURACY, "/key_points"),
            ],
        ),
        _Critic(
            "pedagogy_critic_v0_1",
            [
                (RubricDimension.TEACHING_LOGIC, "/teaching_strategy"),
                (RubricDimension.DIFFERENTIATED_INSTRUCTION, "/differentiation"),
            ],
        ),
        _Critic(
            "alignment_critic_v0_1",
            [
                (RubricDimension.ASSESSMENT_DESIGN, "/assessment_plan"),
                (RubricDimension.CURRICULUM_ALIGNMENT, "/learning_objectives"),
            ],
        ),
    ]
    return AgentSuite(
        execution_mode="live",
        profiles=profiles,
        designer=_Designer(),
        writer=_Writer(),
        critics=critics,
        validator=_Validator(),
        judge=_Judge(),
        rewriter=rewriter,
    )


class GraphIntegrationTests(unittest.TestCase):
    def test_optimize_reviews_high_scoring_uploaded_baseline_before_stopping(self):
        source = make_task()
        task = source.model_copy(update={
            "mode": TaskMode.OPTIMIZE,
            "initial_plan": make_document(source, high_quality=True),
        })
        config = make_config(max_rounds=1, max_model_calls=30,
                             quality_threshold=8.0, critical_dimension_floor=7.0)
        base = _suite(config, _Rewriter())
        suite = AgentSuite(
            execution_mode=base.execution_mode, profiles=base.profiles,
            designer=base.designer, writer=base.writer, critics=base.critics,
            validator=base.validator, judge=_PassingJudge(), rewriter=base.rewriter,
        )
        with tempfile.TemporaryDirectory() as directory:
            result = Paper4Workflow(suite, Path(directory)).run(
                task, config, run_id="optimize-high-baseline"
            )
        self.assertEqual(TaskMode.OPTIMIZE, result.task_mode)
        self.assertGreater(len(result.critiques), 0)
        self.assertGreater(len(result.versions), 1)

    def test_model_call_budget_reserves_configured_retries(self):
        task = make_task()
        config = make_config(
            max_rounds=2, max_model_calls=20,
            generation_review_policy="judge_first_fast_path",
        )
        rewriter = _Rewriter()

        with tempfile.TemporaryDirectory() as directory:
            result = Paper4Workflow(_suite(config, rewriter), Path(directory)).run(
                task, config, run_id="retry-budget-reservation"
            )

        # Three first-attempt bootstrap calls occurred. The next cycle can use
        # 18 attempts (six roles x three configured attempts), so it is stopped
        # before any critic call rather than risking an overrun of 20.
        self.assertEqual(3, result.model_call_count)
        self.assertEqual(StopReason.BUDGET_EXCEEDED, result.stop_reason)
        self.assertEqual([], rewriter.accepted_ids_by_round)

    def test_high_scoring_generated_v0_gets_independent_review_without_fake_rewrite(self):
        task = make_task()
        config = make_config(max_rounds=0, max_model_calls=20)
        base = _suite(config, _Rewriter())
        suite = AgentSuite(
            execution_mode=base.execution_mode, profiles=base.profiles,
            designer=base.designer, writer=base.writer,
            critics=[_Critic(item.profile_id, []) for item in base.critics],
            validator=base.validator, judge=_PassingJudge(),
            rewriter=base.rewriter,
        )
        with tempfile.TemporaryDirectory() as directory:
            result = Paper4Workflow(suite, Path(directory)).run(
                task, config, run_id="high-v0-independent-review"
            )
            events = [
                json.loads(line) for line in Path(result.trace_path).read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
        self.assertEqual(RunStatus.COMPLETED, result.status)
        self.assertEqual(StopReason.NO_ACTIONABLE_FEEDBACK, result.stop_reason)
        self.assertEqual(1, len(result.versions))
        self.assertEqual(1, len(result.validation_batches))
        self.assertEqual(3, len([item for item in events if item["event_type"] == "critic_completed"]))
        self.assertFalse(result.rewrite_records)
        event_types = [item["event_type"] for item in events]
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "p1_high_score_v0_review.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(fixture["event_types"], event_types)
        self.assertEqual(fixture["result"], {
            "status": result.status.value,
            "stop_reason": result.stop_reason.value,
            "best_version_id": result.best_version_id,
            "version_count": len(result.versions),
            "validation_batch_count": len(result.validation_batches),
        })
        self.assertLess(event_types.index("writer_completed"), event_types.index("judge_completed"))
        self.assertLess(event_types.index("judge_completed"), event_types.index("critic_completed"))
        self.assertLess(event_types.index("critic_completed"), event_types.index("validation_completed"))
        self.assertLess(event_types.index("validation_completed"), event_types.index("run_completed"))
        self.assertNotIn("rewrite_completed", event_types)

    def test_reviewed_feedback_with_zero_rewrite_rounds_requires_human(self):
        task = make_task()
        config = make_config(max_rounds=0, max_model_calls=20)
        base = _suite(config, _Rewriter())
        suite = AgentSuite(
            execution_mode=base.execution_mode, profiles=base.profiles,
            designer=base.designer, writer=base.writer, critics=base.critics,
            validator=base.validator, judge=_PassingJudge(),
            rewriter=base.rewriter,
        )
        with tempfile.TemporaryDirectory() as directory:
            result = Paper4Workflow(suite, Path(directory)).run(
                task, config, run_id="reviewed-no-rewrite-budget"
            )
        self.assertEqual(RunStatus.NEEDS_HUMAN, result.status)
        self.assertEqual(StopReason.MAX_ROUNDS, result.stop_reason)
        self.assertEqual(1, len(result.versions))
        self.assertEqual(1, len(result.validation_batches))
        self.assertFalse(result.rewrite_records)

    def test_review_budget_shortfall_keeps_v0_for_human_review(self):
        task = make_task()
        config = make_config(max_model_calls=14)
        base = _suite(config, _Rewriter())
        suite = AgentSuite(
            execution_mode=base.execution_mode, profiles=base.profiles,
            designer=base.designer, writer=base.writer, critics=base.critics,
            validator=base.validator, judge=_PassingJudge(), rewriter=base.rewriter,
        )
        with tempfile.TemporaryDirectory() as directory:
            result = Paper4Workflow(suite, Path(directory)).run(
                task, config, run_id="review-budget-shortfall"
            )
        self.assertEqual(RunStatus.NEEDS_HUMAN, result.status)
        self.assertEqual(StopReason.BUDGET_EXCEEDED, result.stop_reason)
        self.assertEqual(1, len(result.versions))
        self.assertFalse(result.validation_batches)

    def test_fast_path_is_explicit_and_does_not_claim_review(self):
        task = make_task()
        config = make_config(generation_review_policy="judge_first_fast_path")
        base = _suite(config, _Rewriter())
        suite = AgentSuite(
            execution_mode=base.execution_mode, profiles=base.profiles,
            designer=base.designer, writer=base.writer, critics=base.critics,
            validator=base.validator, judge=_PassingJudge(), rewriter=base.rewriter,
        )
        with tempfile.TemporaryDirectory() as directory:
            result = Paper4Workflow(suite, Path(directory)).run(
                task, config, run_id="explicit-fast-path"
            )
        self.assertEqual(StopReason.QUALITY_PASSED, result.stop_reason)
        self.assertFalse(result.validation_batches)
        self.assertFalse(result.critiques)

    def test_too_small_bootstrap_attempt_budget_fails_before_any_artifact(self):
        task = make_task()
        config = make_config(max_model_calls=8)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            workflow = Paper4Workflow(_suite(config, _Rewriter()), output)

            with self.assertRaisesRegex(ValueError, "need at least 9"):
                workflow.run(task, config, run_id="too-small-bootstrap")

            self.assertFalse((output / "too-small-bootstrap").exists())

    def test_partial_critic_node_failure_preserves_prior_usage_and_attempts(self):
        task = make_task()
        config = make_config(max_rounds=1)
        base = _suite(config, _Rewriter())
        suite = AgentSuite(
            execution_mode=base.execution_mode,
            profiles=base.profiles,
            designer=base.designer,
            writer=base.writer,
            critics=[
                _CountedCritic(
                    "subject_critic_v0_1",
                    [(RubricDimension.KNOWLEDGE_ACCURACY, "/content_analysis")],
                ),
                _CountedFailingCritic(),
            ],
            validator=base.validator,
            judge=base.judge,
            rewriter=base.rewriter,
        )

        with tempfile.TemporaryDirectory() as directory:
            result = Paper4Workflow(suite, Path(directory)).run(
                task, config, run_id="partial-critic-failure"
            )

        # design + writer + initial judge + first critic + two failed attempts
        self.assertEqual(6, result.model_call_count)
        self.assertEqual(TokenUsage(input_tokens=18, output_tokens=8), result.token_usage)
        self.assertAlmostEqual(0.6, result.estimated_cost)
        self.assertEqual(RunStatus.FAILED, result.status)
        self.assertEqual(StopReason.RUNTIME_ERROR, result.stop_reason)

    def test_cap_deferred_is_revalidated_next_round_without_duplicate_ids(self):
        task = make_task()
        config = make_config(max_rounds=2, epsilon=0.01)
        rewriter = _Rewriter()
        with tempfile.TemporaryDirectory() as directory:
            workflow = Paper4Workflow(_suite(config, rewriter), Path(directory))
            result = workflow.run(task, config, run_id="cap-replay")

            trace_events = [
                json.loads(line)
                for line in Path(result.trace_path).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            judge_events = [
                event
                for event in trace_events
                if event.get("event_type") == "judge_completed"
            ]

            with self.assertRaises(FileExistsError):
                workflow.run(task, config, run_id="cap-replay")

        self.assertEqual(RunStatus.COMPLETED, result.status)
        self.assertTrue(judge_events)
        self.assertTrue(
            all("task_evidence_profile" in event["input_summary"] for event in judge_events)
        )
        self.assertEqual([5, 1], [len(items) for items in rewriter.accepted_ids_by_round])
        critique_ids = [item.critique_id for item in result.critiques]
        self.assertEqual(len(critique_ids), len(set(critique_ids)))
        carried = next(
            item
            for item in result.critiques
            if item.critique_id == "alignment_critic_v0_1-issue-2"
        )
        self.assertEqual(CritiqueStatus.IMPLEMENTED, carried.status)
        self.assertEqual(
            [
                CritiqueStatus.DEFERRED,
                CritiqueStatus.REOPENED,
                CritiqueStatus.ACCEPTED,
                CritiqueStatus.IMPLEMENTED,
            ],
            [transition.to_status for transition in carried.history],
        )

    def test_rewrite_failure_needs_human_and_marks_accepts_unresolved(self):
        task = make_task()
        config = make_config(max_rounds=1)
        rewriter = _Rewriter(fail=True)
        with tempfile.TemporaryDirectory() as directory:
            workflow = Paper4Workflow(_suite(config, rewriter), Path(directory))
            result = workflow.run(task, config, run_id="rewrite-failure")

        self.assertEqual(RunStatus.NEEDS_HUMAN, result.status)
        self.assertEqual(StopReason.REWRITE_FAILED, result.stop_reason)
        self.assertTrue(result.versions)
        self.assertTrue(result.errors)
        self.assertEqual(RouteAction.HUMAN_REVIEW, result.route_decisions[-1].next_action)
        self.assertEqual(
            {CritiqueStatus.UNRESOLVED, CritiqueStatus.DEFERRED},
            {item.status for item in result.critiques},
        )


if __name__ == "__main__":
    unittest.main()
