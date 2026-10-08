from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from paper4_pipeline.agents.patch_rewriter import (  # noqa: E402
    PatchProposal, ProposedEdit, incremental_patch_rewrite, materialize_patch, patch_rewrite,
)
from paper4_pipeline.agents.patch_rewriter import _editable_path_bases  # noqa: E402
from paper4_pipeline.agents.protocols import AgentCallMetadata  # noqa: E402
from paper4_pipeline.agents.profiles import default_profile_registry  # noqa: E402
from paper4_pipeline.agents.live import LiveRewriter  # noqa: E402
from paper4_pipeline.domain.models import (  # noqa: E402
    RewriteOutcome, TaskMode, TeachingArtifact, TeachingResource, TokenUsage,
)
from paper4_pipeline.providers.openai_compatible import ProviderCallResult  # noqa: E402
from paper4_pipeline.providers.openai_compatible import ProviderInvocationError  # noqa: E402
from support import make_config, make_critique, make_document, make_task, make_version  # noqa: E402


class PatchRewriteTests(unittest.TestCase):
    def test_summary_objects_still_show_canonical_edit_paths(self) -> None:
        self.assertEqual(
            ["/procedure_steps/step-1"],
            _editable_path_bases("/procedure_steps", [{"id": "step-1", "label": "导入"}]),
        )

    def setUp(self) -> None:
        self.task = make_task().model_copy(update={"mode": TaskMode.OPTIMIZE})
        self.document = make_document(self.task, high_quality=True)
        self.critique = make_critique("duration-feasibility").model_copy(update={
            "target_path": "/procedure_steps/0/duration_minutes",
            "issue": "写作任务与当前时间不匹配",
            "actionable_suggestion": "保留时长，减轻任务量并提供支架",
        })

    def test_problem_path_can_stay_unchanged_when_related_activity_is_repaired(self) -> None:
        original_actions = self.document.procedure_steps[0].student_actions
        proposal = PatchProposal(edits=[ProposedEdit(
            critique_id=self.critique.critique_id,
            path="/procedure_steps/0/student_actions",
            value=[*original_actions, "先列两个关键词，再完成简短表达"],
            reason="七分钟内可完成分步写作任务",
        )])
        result = materialize_patch(
            proposal, self.document, [self.critique], self.task, 2,
        )
        self.assertIsInstance(result, RewriteOutcome)
        self.assertEqual(
            self.document.procedure_steps[0].duration_minutes,
            result.document.procedure_steps[0].duration_minutes,
        )
        self.assertNotEqual(original_actions, result.document.procedure_steps[0].student_actions)
        self.assertEqual(
            ["/procedure_steps/0/student_actions"], result.changes[0].edited_paths,
        )
        self.assertEqual(self.critique.target_path, result.changes[0].target_path)
        self.assertEqual("partially_implemented", result.changes[0].implementation_status)

    def test_noop_and_identity_edits_are_rejected(self) -> None:
        no_op = PatchProposal(edits=[ProposedEdit(
            critique_id=self.critique.critique_id,
            path="/procedure_steps/0/student_actions",
            value=self.document.procedure_steps[0].student_actions,
            reason="虚假的修改",
        )])
        with self.assertRaisesRegex(ValueError, "unchanged value"):
            materialize_patch(no_op, self.document, [self.critique], self.task, 2)
        forbidden = PatchProposal(edits=[ProposedEdit(
            critique_id=self.critique.critique_id,
            path="/metadata/subject", value="物理", reason="改科目",
        )])
        with self.assertRaisesRegex(ValueError, "forbidden rewrite path"):
            materialize_patch(forbidden, self.document, [self.critique], self.task, 2)
        virtual_context = PatchProposal(edits=[ProposedEdit(
            critique_id=self.critique.critique_id,
            path="/referenced_context/art-04/content",
            value="虚假修改", reason="输入包装字段不是教案字段",
        )])
        with self.assertRaisesRegex(ValueError, "forbidden rewrite path"):
            materialize_patch(virtual_context, self.document, [self.critique], self.task, 2)

    def test_optimize_duration_issue_routes_to_patch_not_full_document(self) -> None:
        config = make_config()
        profile = default_profile_registry(config.role_model_configs)[config.rewriter_profile_id]
        rewriter = LiveRewriter(profile, Mock())
        version = make_version("v0", 0, score=8.0, task=self.task, document=self.document)
        sentinel = Mock()
        with patch("paper4_pipeline.agents.live.incremental_patch_rewrite", return_value=sentinel) as routed:
            result = rewriter.rewrite(self.task, version, [self.critique], 1)
        self.assertIs(result, sentinel)
        routed.assert_called_once()

    def test_optimize_list_root_still_routes_to_incremental_patch(self) -> None:
        config = make_config()
        profile = default_profile_registry(config.role_model_configs)[config.rewriter_profile_id]
        rewriter = LiveRewriter(profile, Mock())
        version = make_version("v0", 0, score=8.0, task=self.task, document=self.document)
        root_issue = self.critique.model_copy(update={"target_path": "/procedure_steps"})
        with patch("paper4_pipeline.agents.live.incremental_patch_rewrite", return_value=Mock()) as routed:
            rewriter.rewrite(self.task, version, [root_issue], 1)
        routed.assert_called_once()

    def test_failed_issue_does_not_erase_later_valid_edit(self) -> None:
        version = make_version("v0", 0, score=8.0, task=self.task, document=self.document)
        second = make_critique("activity-support").model_copy(update={
            "target_path": "/procedure_steps",
            "issue": "缺少可执行活动",
        })
        proposal = PatchProposal(edits=[ProposedEdit(
            critique_id=second.critique_id,
            path="/procedure_steps/0/student_actions",
            value=[*self.document.procedure_steps[0].student_actions, "先写关键词再表达"],
            reason="增加可完成的学生任务",
        )])
        valid = materialize_patch(proposal, self.document, [second], self.task, 2)
        metadata = AgentCallMetadata(
            provider="stub", model_name="stub", prompt_id="rewrite_patch_prompt",
            prompt_version="1.1", prompt_sha256="a" * 64,
        )
        def one_issue(_provider, _task, _version, critiques, *_args):
            if critiques[0].critique_id == self.critique.critique_id:
                raise ProviderInvocationError(
                    "invalid patch", attempts=1,
                    usage=TokenUsage(input_tokens=30, output_tokens=10),
                    estimated_cost=0.02,
                )
            return __import__("paper4_pipeline.agents.protocols", fromlist=["AgentOutput"]).AgentOutput(
                value=valid,
                usage=TokenUsage(input_tokens=100, output_tokens=50),
                estimated_cost=0.03,
                metadata=metadata,
            )
        with patch("paper4_pipeline.agents.patch_rewriter.patch_rewrite", side_effect=one_issue):
            output = incremental_patch_rewrite(
                Mock(), self.task, version, [self.critique, second], 1, 2,
            )
        self.assertEqual([second.critique_id], [change.critique_id for change in output.value.changes])
        self.assertEqual([self.critique.critique_id], output.value.unresolved_critique_ids)
        self.assertNotEqual(version.document, output.value.document)
        self.assertEqual(2, output.metadata.attempts)
        self.assertEqual(130, output.usage.input_tokens)
        self.assertAlmostEqual(0.05, output.estimated_cost)

    def test_no_effect_never_returns_fake_new_version(self) -> None:
        version = make_version("v0", 0, score=8.0, task=self.task, document=self.document)
        with patch("paper4_pipeline.agents.patch_rewriter.patch_rewrite", side_effect=
                   ProviderInvocationError("invalid patch", attempts=1,
                       usage=TokenUsage(input_tokens=30, output_tokens=10),
                       estimated_cost=0.02)):
            with self.assertRaisesRegex(ProviderInvocationError, "no effective lesson-plan edit") as caught:
                incremental_patch_rewrite(Mock(), self.task, version, [self.critique], 1, 2)
        self.assertEqual(1, caught.exception.attempts)
        self.assertEqual(30, caught.exception.usage.input_tokens)

    def test_root_issue_sends_only_referenced_step_not_entire_lesson(self) -> None:
        version = make_version("v0", 0, score=8.0, task=self.task, document=self.document)
        issue = self.critique.model_copy(update={
            "target_path": "/procedure_steps",
            "issue": "step-2 的学生任务需要更具体",
            "evidence": "step-2 缺少可观察产出",
            "actionable_suggestion": "修改 step-2 的 student_actions",
        })
        provider = Mock()
        proposal = PatchProposal(unresolved_critique_ids=[issue.critique_id])
        def answer(**kwargs):
            focus = kwargs["input_payload"]["accepted_feedback_and_local_source"][0]
            self.assertEqual("/procedure_steps", focus["parent_path"])
            self.assertEqual(["step-2"], [item["step_id"] for item in focus["parent_content"]])
            self.assertEqual(["/procedure_steps/step-2"], focus["editable_path_bases"])
            self.assertEqual(2, kwargs["max_attempts"])
            self.assertEqual(7168, kwargs["max_output_tokens"])
            self.assertIn("teaching_artifact", kwargs["input_payload"]["field_contracts"])
            kwargs["result_validator"](proposal)
            return ProviderCallResult(
                value=proposal, usage=TokenUsage(), estimated_cost=0.0,
                metadata=AgentCallMetadata(
                    provider="stub", model_name="stub", prompt_id="rewrite_patch_prompt",
                    prompt_version="1.1", prompt_sha256="a" * 64,
                ),
            )
        provider.invoke_structured.side_effect = answer
        result = patch_rewrite(provider, self.task, version, [issue], 1, 2)
        self.assertEqual([issue.critique_id], result.value.unresolved_critique_ids)

    def test_reference_payload_keeps_resource_and_artifact_paths_distinct(self) -> None:
        shared_id = "shared-01"
        self.document.resources.append(TeachingResource(
            resource_id=shared_id, name="计时器", ready_to_use_content="原资源说明",
        ))
        self.document.teaching_artifacts.append(TeachingArtifact(
            artifact_id=shared_id, artifact_type="任务单", title="课堂任务单",
            content="原任务单正文",
        ))
        version = make_version("v0", 0, score=8.0, task=self.task, document=self.document)
        issue = self.critique.model_copy(update={
            "target_path": "/teaching_artifacts",
            "issue": f"{shared_id} 的资源说明和任务单都需要完善",
        })
        proposal = PatchProposal(edits=[
            ProposedEdit(critique_id=issue.critique_id,
                         path="/resources/shared-01/ready_to_use_content",
                         value="教师用计时器提示还剩两分钟", reason="说明教师动作"),
            ProposedEdit(critique_id=issue.critique_id,
                         path="/teaching_artifacts/shared-01/content",
                         value="任务单：观察、记录证据并写一句解释。", reason="补充学生材料"),
        ])
        provider = Mock()

        def answer(**kwargs):
            payload = kwargs["input_payload"]
            refs = payload["referenced_context"]
            self.assertEqual(2, len(refs))
            self.assertEqual(
                {("resource", "/resources/shared-01"),
                 ("teaching_artifact", "/teaching_artifacts/shared-01")},
                {(ref["kind"], ref["editable_path_base"]) for ref in refs},
            )
            self.assertTrue(all(ref["id"] == shared_id for ref in refs))
            self.assertEqual(
                ["/teaching_artifacts/shared-01"],
                payload["accepted_feedback_and_local_source"][0]["editable_path_bases"],
            )
            kwargs["result_validator"](proposal)
            return ProviderCallResult(
                value=proposal, usage=TokenUsage(), estimated_cost=0.0,
                metadata=AgentCallMetadata(
                    provider="stub", model_name="stub", prompt_id="rewrite_patch_prompt",
                    prompt_version="1.2", prompt_sha256="a" * 64,
                ),
            )

        provider.invoke_structured.side_effect = answer
        output = patch_rewrite(provider, self.task, version, [issue], 1, 2)
        self.assertEqual(
            "教师用计时器提示还剩两分钟",
            output.value.document.resources[-1].ready_to_use_content,
        )
        self.assertEqual(
            "任务单：观察、记录证据并写一句解释。",
            output.value.document.teaching_artifacts[-1].content,
        )

    def test_patch_model_call_is_validated_and_returns_real_rewrite_outcome(self) -> None:
        version = make_version("v0", 0, score=8.0, task=self.task, document=self.document)
        proposal = PatchProposal(edits=[ProposedEdit(
            critique_id=self.critique.critique_id,
            path="/procedure_steps/0/student_actions",
            value=[*self.document.procedure_steps[0].student_actions, "先写关键词，再写一句话"],
            reason="降低限时任务负担",
        )])
        provider = Mock()
        def answer(**kwargs):
            kwargs["result_validator"](proposal)
            return ProviderCallResult(
                value=proposal,
                usage=TokenUsage(input_tokens=120, output_tokens=60),
                estimated_cost=0.01,
                metadata=AgentCallMetadata(
                    provider="stub", model_name="stub", prompt_id="rewrite_patch_prompt",
                    prompt_version="1.0", prompt_sha256="a" * 64,
                ),
            )
        provider.invoke_structured.side_effect = answer
        output = patch_rewrite(provider, self.task, version, [self.critique], 1, 2)
        self.assertNotEqual(version.document, output.value.document)
        self.assertEqual(1, len(output.value.changes))
        self.assertEqual("rewrite_patch", provider.invoke_structured.call_args.kwargs["stage"])

    def test_local_patch_can_improve_an_imperfect_import_incrementally(self) -> None:
        """Unrelated baseline defects must not make every local edit impossible."""

        imperfect_task = self.task.model_copy(update={
            "required_sections": ["assessment_plan", "differentiation"],
        })
        imperfect = self.document.model_copy(update={
            "assessment_plan": "",
            "differentiation": "",
        })
        original_actions = imperfect.procedure_steps[0].student_actions
        proposal = PatchProposal(edits=[ProposedEdit(
            critique_id=self.critique.critique_id,
            path="/procedure_steps/step-1/student_actions",
            value=[*original_actions, "用一句话写出判断依据，再与同伴互证。"],
            reason="补充可观察的学习证据",
        )])

        outcome = materialize_patch(
            proposal, imperfect, [self.critique], imperfect_task, 2,
        )

        self.assertNotEqual(imperfect, outcome.document)
        self.assertEqual("", outcome.document.assessment_plan)
        self.assertEqual("", outcome.document.differentiation)

    def test_local_patch_still_rejects_a_new_hard_rule_regression(self) -> None:
        proposal = PatchProposal(edits=[ProposedEdit(
            critique_id=self.critique.critique_id,
            path="/procedure_steps/step-1/duration_minutes",
            value=1,
            reason="错误地破坏总课时",
        )])

        with self.assertRaisesRegex(ValueError, "hard-rule regression"):
            materialize_patch(
                proposal, self.document, [self.critique], self.task, 2,
            )


if __name__ == "__main__":
    unittest.main()
