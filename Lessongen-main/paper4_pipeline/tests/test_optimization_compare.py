from __future__ import annotations

import sys
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from paper4_pipeline.agents.optimization_compare import PairwiseVote, compare  # noqa: E402
from paper4_pipeline.agents.protocols import AgentCallMetadata  # noqa: E402
from paper4_pipeline.domain.models import TaskMode, TokenUsage  # noqa: E402
from paper4_pipeline.providers.openai_compatible import (  # noqa: E402
    ProviderCallResult, ProviderInvocationError,
)
from support import make_document, make_task, make_version  # noqa: E402


def _vote(
    preferred: str,
    *,
    progress: str = "improved",
    substantive: bool = True,
    regressions: list[str] | None = None,
) -> PairwiseVote:
    return PairwiseVote(
        preferred=preferred,
        substantive_progress=substantive,
        target_issue_progress=progress,
        regression_flags=regressions or [],
        evidence=["B 的评价证据由笼统描述改为可观察学生作品。"],
        rationale="比较评价环节中的真实学生产出与判据。",
    )


class FakeProvider:
    def __init__(self, replies: list[PairwiseVote | Exception]):
        self.replies = list(replies)
        self.calls: list[dict[str, object]] = []

    def invoke_structured(self, **kwargs: object) -> ProviderCallResult[PairwiseVote]:
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return ProviderCallResult(
            value=reply,
            usage=TokenUsage(input_tokens=100, output_tokens=25),
            estimated_cost=0.01,
            metadata=AgentCallMetadata(
                provider="fake", model_name="fake", prompt_id="optimization_compare_prompt",
                prompt_version="1.0", prompt_sha256="f" * 64,
                response_id=f"response-{len(self.calls)}", attempts=1,
            ),
        )


class OptimizationCompareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = make_task().model_copy(update={"mode": TaskMode.OPTIMIZE})
        self.baseline_document = make_document(self.task, high_quality=True)
        self.candidate_document = self.baseline_document.model_copy(update={
            "assessment_plan": (
                "用出口卡记录学生是否能指出单位一、写出相应分数并解释分母的意义；"
                "根据三项证据决定下一课时的支架。"
            ),
        })
        self.baseline = make_version(
            "v0", 0, score=7.7, task=self.task, document=self.baseline_document,
        )
        self.candidate = make_version(
            "v1", 1, score=7.7, task=self.task,
            document=self.candidate_document, parent_version_id="v0",
        )

    def test_swapped_votes_support_substantive_candidate_and_count_usage(self) -> None:
        provider = FakeProvider([_vote("B", progress="worse"), _vote("A", progress="improved")])
        result = compare(provider, self.task, self.baseline, self.candidate)
        self.assertEqual("candidate_preferred", result.value.verdict)
        self.assertTrue(result.value.candidate_preferred)
        self.assertEqual("improved", result.value.target_issue_progress)
        self.assertEqual(["assessment_plan"], result.value.changed_sections)
        self.assertEqual(200, result.usage.input_tokens)
        self.assertEqual(50, result.usage.output_tokens)
        self.assertAlmostEqual(0.02, result.estimated_cost)
        self.assertEqual(2, result.metadata.attempts)
        self.assertEqual(2, len(provider.calls))
        for call in provider.calls:
            self.assertEqual(1, call["max_attempts"])
            self.assertLessEqual(call["max_output_tokens"], 2048)
        first, second = [call["input_payload"] for call in provider.calls]
        self.assertEqual(
            self.baseline_document.assessment_plan,
            first["A"]["focus_content"]["assessment_plan"],
        )
        self.assertEqual(
            self.baseline_document.assessment_plan,
            second["B"]["focus_content"]["assessment_plan"],
        )

    def test_same_content_never_passes_on_score_drift(self) -> None:
        provider = FakeProvider([])
        result = compare(provider, self.task, self.baseline, self.baseline)
        self.assertEqual("uncertain", result.value.verdict)
        self.assertIn("No canonical lesson-plan content changed", result.value.reason)
        self.assertEqual([], provider.calls)
        self.assertIsNone(result.metadata)

    def test_order_disagreement_is_uncertain(self) -> None:
        provider = FakeProvider([_vote("B"), _vote("B")])
        result = compare(provider, self.task, self.baseline, self.candidate)
        self.assertEqual("uncertain", result.value.verdict)
        self.assertEqual(
            ["candidate", "baseline"],
            [vote.preference for vote in result.value.votes],
        )

    def test_one_failed_vote_is_uncertain_and_usage_is_preserved(self) -> None:
        failed = ProviderInvocationError(
            "api failure", attempts=1,
            usage=TokenUsage(input_tokens=70, output_tokens=5),
            estimated_cost=0.004,
        )
        provider = FakeProvider([_vote("B"), failed])
        result = compare(provider, self.task, self.baseline, self.candidate)
        self.assertEqual("uncertain", result.value.verdict)
        self.assertEqual(1, result.value.failed_calls)
        self.assertEqual(170, result.usage.input_tokens)
        self.assertEqual(30, result.usage.output_tokens)
        self.assertAlmostEqual(0.014, result.estimated_cost)
        self.assertEqual(2, result.metadata.attempts)

    def test_candidate_regression_vetoes_positive_votes(self) -> None:
        provider = FakeProvider([
            _vote("B", progress="worse", regressions=["活动可能超出 45 分钟"]),
            _vote("A"),
        ])
        result = compare(provider, self.task, self.baseline, self.candidate)
        self.assertEqual("uncertain", result.value.verdict)
        self.assertEqual(["活动可能超出 45 分钟"], result.value.regression_flags)

    def test_two_baseline_votes_can_reject_candidate(self) -> None:
        provider = FakeProvider([
            _vote("A", progress="improved", substantive=False),
            _vote("B", progress="worse", substantive=False),
        ])
        result = compare(provider, self.task, self.baseline, self.candidate)
        self.assertEqual("baseline_preferred", result.value.verdict)
        self.assertEqual("worse", result.value.target_issue_progress)

    def test_no_external_doc_in_comparison_output(self) -> None:
        provider = FakeProvider([_vote("B", progress="worse"), _vote("A")])
        result = compare(provider, self.task, self.baseline, self.candidate)
        serialized = result.value.model_dump_json()
        self.assertNotIn("出口卡记录学生", serialized)
        self.assertNotIn("unit-math-fractions-plan", serialized)

    def test_metadata_or_hard_rule_failure_cannot_be_certified(self) -> None:
        provider = FakeProvider([])
        changed_metadata = self.candidate_document.model_copy(update={
            "metadata": self.candidate_document.metadata.model_copy(update={
                "subject": "语文",
            }),
        })
        changed_version = self.candidate.model_copy(update={"document": changed_metadata})
        result = compare(provider, self.task, self.baseline, changed_version)
        self.assertEqual("uncertain", result.value.verdict)
        self.assertIn("identity", result.value.reason)
        bad_rules = self.candidate.rule_check_report.model_copy(update={"passed": False})
        invalid_version = self.candidate.model_copy(update={"rule_check_report": bad_rules})
        result = compare(provider, self.task, self.baseline, invalid_version)
        self.assertEqual("uncertain", result.value.verdict)
        self.assertIn("deterministic", result.value.reason)
        self.assertEqual([], provider.calls)


if __name__ == "__main__":
    unittest.main()
