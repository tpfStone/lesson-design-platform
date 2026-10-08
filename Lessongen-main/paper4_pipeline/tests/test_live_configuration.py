from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from support import make_config, make_critique, make_document, make_task, make_version

from paper4_pipeline.agents.live import (
    CritiqueProposal,
    CritiqueProposalSet,
    ValidationProposalSet,
    _validate_critic_batch,
    build_live_suite,
)
from paper4_pipeline.agents.prompts import PROMPT_FILES, load_prompt
from paper4_pipeline.control.alignment import build_alignment_audit
from paper4_pipeline.control.evidence import build_task_evidence_profile
from paper4_pipeline.control.rules import lesson_target_changed
from paper4_pipeline.knowledge.registry import build_knowledge_bundle
from paper4_pipeline.domain.models import CritiqueBatch, ModelConfig, RubricDimension
from paper4_pipeline.providers.openai_compatible import (
    OpenAICompatibleProvider,
    ProviderInvocationError,
)
from paper4_pipeline.observability.call_ledger import activate_call_ledger


class _RetryPayload(BaseModel):
    value: int = Field(ge=1)


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content
        self.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
        self.response_metadata = {"finish_reason": "stop"}
        self.id = "fake-response"


class _FakeJsonClient:
    def __init__(self) -> None:
        self.responses = iter([_FakeMessage('{"value": 0}'), _FakeMessage('{"value": 1}')])
        self.calls: list[list[object]] = []

    def bind(self, **_: object) -> "_FakeJsonClient":
        return self

    def invoke(self, messages: list[object]) -> _FakeMessage:
        self.calls.append(messages)
        return next(self.responses)


class _PaymentRequiredError(Exception):
    status_code = 402


class _PaymentRequiredClient:
    def __init__(self) -> None:
        self.calls = 0

    def bind(self, **_: object) -> "_PaymentRequiredClient":
        return self

    def invoke(self, messages: list[object]) -> _FakeMessage:
        self.calls += 1
        raise _PaymentRequiredError("Insufficient Balance")


class _LengthLimitedClient:
    def __init__(self) -> None:
        self.calls = 0

    def bind(self, **_: object) -> "_LengthLimitedClient":
        return self

    def invoke(self, messages: list[object]) -> _FakeMessage:
        self.calls += 1
        raise RuntimeError(
            "length limit was reached - CompletionUsage("
            "completion_tokens=8192, prompt_tokens=1200, total_tokens=9392)"
        )


class LiveConfigurationTests(unittest.TestCase):
    def test_validator_retry_identifies_invalid_merge_and_valid_targets(self) -> None:
        suite = build_live_suite(make_config())
        version = make_version("v0", 0, score=7.0)
        critiques = CritiqueBatch(
            batch_id="batch-test", plan_version_id=version.version_id, round_index=1,
            items=[make_critique(key) for key in ("source", "rejected", "accepted")],
        )
        proposals = ValidationProposalSet.model_validate({"decisions": [
            {"critique_id": key, "decision": decision, "grounded": True,
             "relevant": True, "actionable": True, "reason": "fixture",
             "canonical_critique_id": "rejected" if key == "source" else ""}
            for key, decision in (("source", "merge"), ("rejected", "reject"),
                                  ("accepted", "accept"))
        ]})
        provider = Mock()
        provider.invoke_structured.side_effect = (
            lambda **kwargs: kwargs["result_validator"](proposals)
        )
        suite.validator.provider = provider
        with self.assertRaises(ValueError) as caught:
            suite.validator.validate(make_task(), version, critiques, 1)
        message = str(caught.exception)
        self.assertIn("critique 'source'", message)
        self.assertIn("target 'rejected' has decision 'reject'", message)
        self.assertIn("Current accepted target IDs: ['accepted']", message)
        self.assertIn("clear canonical_critique_id", message)
        self.assertEqual("reject", proposals.decisions[1].decision.value)

    def test_validator_retry_reports_exact_missing_duplicate_and_extra_ids(self) -> None:
        suite = build_live_suite(make_config())
        version = make_version("v0", 0, score=7.0)
        critiques = CritiqueBatch(
            batch_id="batch-coverage", plan_version_id=version.version_id, round_index=1,
            items=[make_critique(key) for key in ("source", "second", "third")],
        )
        proposal = ValidationProposalSet.model_validate({"decisions": [
            {"critique_id": key, "decision": "defer", "grounded": False,
             "relevant": True, "actionable": False, "reason": "insufficient evidence"}
            for key in ("source", "source", "unexpected")
        ]})
        provider = Mock()
        provider.invoke_structured.side_effect = (
            lambda **kwargs: kwargs["result_validator"](proposal)
        )
        suite.validator.provider = provider
        with self.assertRaises(ValueError) as caught:
            suite.validator.validate(make_task(), version, critiques, 1)
        message = str(caught.exception)
        self.assertIn("missing_ids=['second', 'third']", message)
        self.assertIn("duplicate_ids=['source']", message)
        self.assertIn("unexpected_ids=['unexpected']", message)
        payload = provider.invoke_structured.call_args.kwargs["input_payload"]
        self.assertEqual(["source", "second", "third"], payload["required_critique_ids"])
        self.assertEqual(3, payload["required_decision_count"])

    def test_deepseek_request_preserves_output_limit_and_thinking_mode(self) -> None:
        for override in (None, 2048):
            with self.subTest(max_output_tokens=override):
                requests: list[dict[str, object]] = []

                def respond(request: httpx.Request) -> httpx.Response:
                    requests.append(json.loads(request.content))
                    return httpx.Response(200, json={
                        "id": "unit-response",
                        "object": "chat.completion",
                        "created": 1,
                        "model": "deepseek-v4-flash",
                        "choices": [{"index": 0, "finish_reason": "stop",
                                     "message": {"role": "assistant", "content": '{"value": 1}'}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    })

                with (
                    httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as transport,
                    patch.dict(os.environ, {
                        "DEEPSEEK_API_KEY": "unit-test-key",
                        "DEEPSEEK_BASE_URL": "https://deepseek.example",
                    }, clear=True),
                    patch.object(OpenAICompatibleProvider, "load_environment"),
                    patch("paper4_pipeline.providers.openai_compatible.ChatOpenAI",
                          side_effect=lambda **kwargs: ChatOpenAI(**kwargs, http_client=transport)),
                ):
                    provider = OpenAICompatibleProvider(ModelConfig(max_tokens=12288))
                    result = provider.invoke_structured(
                        prompt=load_prompt("writer_prompt"),
                        input_payload={"fixture": True},
                        output_schema=_RetryPayload,
                        stage="unit_output_limit",
                        max_output_tokens=override,
                    )

                self.assertEqual(1, result.value.value)
                self.assertEqual(1, len(requests))
                self.assertEqual(override or 12288, requests[0].get("max_tokens"))
                self.assertNotIn("max_completion_tokens", requests[0])
                self.assertEqual({"type": "disabled"}, requests[0]["thinking"])

    def test_every_model_backed_role_is_real_deepseek_v4_flash(self) -> None:
        config = make_config()
        suite = build_live_suite(config)

        self.assertEqual("live", suite.execution_mode)
        self.assertEqual(8, len(suite.profiles))
        self.assertEqual(
            {"deepseek-v4-flash"},
            {profile.model.model_name for profile in suite.profiles.values()},
        )

    def test_versioned_prompts_are_substantial_and_hashed(self) -> None:
        for prompt_id in PROMPT_FILES:
            prompt = load_prompt(prompt_id)
            expected = {
                "design_architect_prompt": "1.0",
                "writer_prompt": "1.3",
                "pedagogy_critic_prompt": "1.3",
                "alignment_critic_prompt": "1.1",
                "validator_prompt": "1.6",
                "judge_prompt": "1.3",
                "rewriter_prompt": "1.6",
                "rewrite_patch_prompt": "1.3",
                "docx_normalizer_prompt": "1.1",
                "docx_overview_prompt": "1.0",
                "docx_activities_prompt": "1.0",
            }.get(prompt_id, "1.2")
            self.assertEqual(expected, prompt.version)
            self.assertGreater(len(prompt.content), 500)
            self.assertEqual(64, len(prompt.sha256))
            self.assertIn("输出契约", prompt.content)

    def test_profile_prompt_versions_match_loaded_prompt_versions(self) -> None:
        suite = build_live_suite(make_config())

        for profile in suite.profiles.values():
            self.assertEqual(
                load_prompt(profile.prompt_id).version,
                profile.prompt_version,
                profile.profile_id,
            )

    def test_creative_prompt_keeps_freedom_inside_hard_boundaries(self) -> None:
        writer = load_prompt("writer_prompt")
        rewriter = load_prompt("rewriter_prompt")

        self.assertIn("创造性自由", writer.content)
        self.assertIn("不要默认套用固定五段式", writer.content)
        self.assertIn("保留创意主线", rewriter.content)
        self.assertIn("artifact_ids", writer.content)
        self.assertIn("不得跨命名空间引用", rewriter.content)

    def test_validator_prompt_requires_cross_critic_deduplication(self) -> None:
        validator = load_prompt("validator_prompt")

        self.assertIn("先横向比较整批意见", validator.content)
        self.assertIn("不得仅因来自不同 Critic 就分别接受", validator.content)

    def test_role_knowledge_is_heterogeneous_and_auditable(self) -> None:
        task = make_task()
        suite = build_live_suite(make_config())
        source_sets = {
            role: set(build_knowledge_bundle(profile, task).source_ids)
            for role, profile in suite.profiles.items()
        }

        self.assertIn("textbook", source_sets["subject_critic_v0_1"])
        self.assertNotIn("textbook", source_sets["pedagogy_critic_v0_1"])
        self.assertIn(
            "alignment_protocol_v0_1",
            source_sets["alignment_critic_v0_1"],
        )
        self.assertIn("rubric_v0_1", source_sets["judge_v0_1"])
        self.assertIn("rewrite_rules", source_sets["rewriter_v0_1"])
        self.assertIn(
            "lesson_design_reference_v1_2",
            source_sets["design_architect_v0_1"],
        )

    def test_three_critics_have_non_overlapping_primary_dimensions(self) -> None:
        suite = build_live_suite(make_config())
        subject = suite.profiles["subject_critic_v0_1"]
        pedagogy = suite.profiles["pedagogy_critic_v0_1"]
        alignment = suite.profiles["alignment_critic_v0_1"]

        self.assertEqual(
            {RubricDimension.KNOWLEDGE_ACCURACY},
            set(subject.rubric_dimensions),
        )
        self.assertEqual(
            {
                RubricDimension.CURRICULUM_ALIGNMENT,
                RubricDimension.ASSESSMENT_DESIGN,
            },
            set(alignment.rubric_dimensions),
        )
        self.assertTrue(
            set(pedagogy.rubric_dimensions).isdisjoint(alignment.rubric_dimensions)
        )

    def test_alignment_audit_exposes_traceability_gaps(self) -> None:
        task = make_task()
        document = make_document(task)
        audit = build_alignment_audit(document, task)
        warning_codes = {item["code"] for item in audit["warnings"]}

        self.assertEqual(
            "objective-activity-evidence-v0.2",
            audit["audit_version"],
        )
        self.assertIn("objectives_without_evidence", warning_codes)
        self.assertIn("steps_without_success_criteria", warning_codes)
        self.assertEqual(
            "obj-1",
            audit["objective_traceability"][0]["objective_id"],
        )

    def test_alignment_audit_marks_absent_standards_as_input_limitation(self) -> None:
        source_task = make_task()
        document = make_document(source_task)
        task = source_task.model_copy(update={"curriculum_standards": []})
        document.curriculum_standards = []
        for objective in document.learning_objectives:
            objective.standard_refs = []

        audit = build_alignment_audit(document, task)
        warning_codes = {item["code"] for item in audit["warnings"]}
        limitation_codes = {item["code"] for item in audit["input_limitations"]}

        self.assertNotIn("objectives_without_standard_refs", warning_codes)
        self.assertIn("task_curriculum_standards_unavailable", limitation_codes)

    def test_task_evidence_profile_keeps_missing_sources_separate_from_quality(self) -> None:
        source = make_task()
        task = source.model_copy(
            update={
                "curriculum_standards": [],
                "textbook_content": "",
                "student_profile": "",
                "learning_objectives": [],
            }
        )

        profile = build_task_evidence_profile(task)

        self.assertEqual("minimal", profile["readiness_level"])
        self.assertEqual(4, len(profile["missing_fields"]))
        self.assertTrue(profile["scoring_policy"]["keep_all_eight_dimensions"])
        self.assertIn("内部", profile["scoring_policy"]["curriculum_alignment"])

    def test_structured_retry_shows_model_its_previous_invalid_json(self) -> None:
        provider = OpenAICompatibleProvider(ModelConfig(max_retries=1))
        client = _FakeJsonClient()
        provider._client = client  # type: ignore[assignment]

        with tempfile.TemporaryDirectory() as directory:
            with activate_call_ledger(Path(directory) / "attempts.jsonl") as ledger:
                result = provider.invoke_structured(
                    prompt=load_prompt("validator_prompt"),
                    input_payload={"fixture": True},
                    output_schema=_RetryPayload,
                    stage="unit_retry",
                )
            self.assertEqual(["invalid_output", "ok"], [item.status for item in ledger.records])
            self.assertEqual(20, sum(item.input_tokens or 0 for item in ledger.records))
            self.assertEqual(10, sum(item.output_tokens or 0 for item in ledger.records))
            self.assertEqual(2, len({item.attempt_id for item in ledger.records}))
            self.assertEqual(1, len({item.call_id for item in ledger.records}))
            self.assertEqual("provider_response", ledger.records[0].usage_source)
            self.assertEqual(result.usage.input_tokens, sum(item.input_tokens or 0 for item in ledger.records))
            self.assertEqual(result.usage.output_tokens, sum(item.output_tokens or 0 for item in ledger.records))
            self.assertAlmostEqual(result.estimated_cost, sum(item.estimated_cost or 0 for item in ledger.records))

        self.assertEqual(1, result.value.value)
        self.assertEqual(2, result.metadata.attempts)
        self.assertEqual(2, len(client.calls))
        retry_messages = client.calls[1]
        self.assertTrue(any(isinstance(item, AIMessage) for item in retry_messages))
        self.assertTrue(
            any("校验错误" in str(getattr(item, "content", "")) for item in retry_messages)
        )

    def test_payment_required_fails_fast_without_three_identical_attempts(self) -> None:
        provider = OpenAICompatibleProvider(ModelConfig(max_retries=2))
        client = _PaymentRequiredClient()
        provider._client = client  # type: ignore[assignment]

        with tempfile.TemporaryDirectory() as directory:
            with activate_call_ledger(Path(directory) / "attempts.jsonl") as ledger:
                with self.assertRaises(ProviderInvocationError) as raised:
                    provider.invoke_structured(
                        prompt=load_prompt("validator_prompt"),
                        input_payload={"fixture": True},
                        output_schema=_RetryPayload,
                        stage="unit_payment_required",
                    )
            self.assertEqual(1, len(ledger.records))
            self.assertEqual("failed", ledger.records[0].status)
            self.assertIsNone(ledger.records[0].input_tokens)
            self.assertIsNone(ledger.records[0].estimated_cost)

        self.assertEqual(1, raised.exception.attempts)
        self.assertEqual(1, client.calls)
        self.assertIn("Insufficient Balance", str(raised.exception))

    def test_success_without_provider_usage_records_unknown_not_zero(self) -> None:
        provider = OpenAICompatibleProvider(ModelConfig(max_retries=1))
        client = _FakeJsonClient()
        message = _FakeMessage('{"value": 1}')
        message.usage_metadata = {}
        client.responses = iter([message])
        provider._client = client  # type: ignore[assignment]
        with tempfile.TemporaryDirectory() as directory:
            with activate_call_ledger(Path(directory) / "attempts.jsonl") as ledger:
                result = provider.invoke_structured(
                    prompt=load_prompt("validator_prompt"),
                    input_payload={"fixture": True},
                    output_schema=_RetryPayload,
                    stage="unit_unknown_usage",
                )
        self.assertEqual(1, result.value.value)
        self.assertEqual(1, len(ledger.records))
        self.assertIsNone(ledger.records[0].input_tokens)
        self.assertIsNone(ledger.records[0].estimated_cost)
        self.assertEqual("unknown", ledger.records[0].usage_source)

    def test_ledger_write_failure_never_retries_a_paid_call(self) -> None:
        provider = OpenAICompatibleProvider(ModelConfig(max_retries=2))
        client = _FakeJsonClient()
        client.responses = iter([_FakeMessage('{"value": 1}')])
        provider._client = client  # type: ignore[assignment]
        with tempfile.TemporaryDirectory() as directory:
            with activate_call_ledger(Path(directory) / "attempts.jsonl") as ledger:
                with patch.object(ledger, "append", side_effect=OSError("disk full")):
                    with self.assertRaisesRegex(
                        ProviderInvocationError, "accounting could not be persisted"
                    ) as raised:
                        provider.invoke_structured(
                            prompt=load_prompt("validator_prompt"),
                            input_payload={"fixture": True},
                            output_schema=_RetryPayload,
                            stage="unit_ledger_failure",
                        )
        self.assertEqual(1, len(client.calls))
        self.assertEqual(1, raised.exception.attempts)
        self.assertEqual(10, raised.exception.usage.input_tokens)

    def test_graceful_cancellation_records_unknown_attempt_without_retry(self) -> None:
        provider = OpenAICompatibleProvider(ModelConfig(max_retries=2))
        client = _PaymentRequiredClient()
        client.invoke = Mock(side_effect=KeyboardInterrupt())
        provider._client = client  # type: ignore[assignment]
        with tempfile.TemporaryDirectory() as directory:
            with activate_call_ledger(Path(directory) / "attempts.jsonl") as ledger:
                with self.assertRaises(KeyboardInterrupt):
                    provider.invoke_structured(
                        prompt=load_prompt("validator_prompt"),
                        input_payload={"fixture": True},
                        output_schema=_RetryPayload,
                        stage="unit_cancelled",
                    )
        self.assertEqual(1, client.invoke.call_count)
        self.assertEqual(1, len(ledger.records))
        self.assertEqual("cancelled", ledger.records[0].status)
        self.assertIsNone(ledger.records[0].input_tokens)

    def test_rewriter_output_cap_stops_and_counts_paid_tokens(self) -> None:
        provider = OpenAICompatibleProvider(ModelConfig(max_retries=2))
        client = _LengthLimitedClient()
        provider._client = client  # type: ignore[assignment]

        with tempfile.TemporaryDirectory() as directory:
            with activate_call_ledger(Path(directory) / "attempts.jsonl") as ledger:
                with self.assertRaises(ProviderInvocationError) as raised:
                    provider.invoke_structured(
                        prompt=load_prompt("rewrite_patch_prompt"),
                        input_payload={"fixture": True},
                        output_schema=_RetryPayload,
                        stage="rewrite_patch",
                    )
            self.assertEqual(1, len(ledger.records))
            self.assertEqual("truncated", ledger.records[0].status)
            self.assertEqual("truncation_exception", ledger.records[0].usage_source)
            self.assertEqual(8192, ledger.records[0].output_tokens)
            self.assertEqual(raised.exception.usage.input_tokens, ledger.records[0].input_tokens)
            self.assertAlmostEqual(raised.exception.estimated_cost, ledger.records[0].estimated_cost)

        self.assertEqual(1, client.calls)
        self.assertEqual(1, raised.exception.attempts)
        self.assertEqual(1200, raised.exception.usage.input_tokens)
        self.assertEqual(8192, raised.exception.usage.output_tokens)

    def test_duration_tolerance_minutes_threads_into_writer_and_rewriter(self) -> None:
        # Regression: build_live_suite used to drop the config tolerance, so the
        # model-retry boundary always enforced the hard-coded default of 2 even
        # when the config widened it (making live runs stricter than the graph).
        suite = build_live_suite(make_config(duration_tolerance_minutes=9))

        self.assertEqual(9, suite.writer.duration_tolerance_minutes)
        self.assertEqual(9, suite.rewriter.duration_tolerance_minutes)

        default_suite = build_live_suite(make_config())
        self.assertEqual(2, default_suite.writer.duration_tolerance_minutes)
        self.assertEqual(2, default_suite.rewriter.duration_tolerance_minutes)

    def test_claimed_rewrite_target_must_observably_change(self) -> None:
        original = make_document(make_task(), high_quality=True)
        candidate = original.model_copy(deep=True)

        self.assertFalse(
            lesson_target_changed(original, candidate, "/assessment_plan")
        )
        self.assertFalse(
            lesson_target_changed(original, candidate, "/procedure_steps/not-an-id")
        )

        candidate.procedure_steps[0].assessment += " 增加即时口头复述证据。"
        self.assertTrue(
            lesson_target_changed(
                original,
                candidate,
                "/procedure_steps/step-1/assessment",
            )
        )


class CriticKnowledgeCitationTests(unittest.TestCase):
    """A critic may cite a knowledge source by its declared source id OR by a
    retrieved fragment's id.  The bundle JSON handed to the model shows both
    handles, so rejecting the fragment handle is a contract mismatch that
    crashed round-1 runs with ``critic cited unknown knowledge sources``."""

    _KNOWN = {"task_context", "textbook", "fragment-16d8e49aeb9b"}

    @staticmethod
    def _proposal(dimension: RubricDimension, refs: list[str]) -> CritiqueProposal:
        return CritiqueProposal(
            dimension=dimension,
            issue_code="knowledge_source_handling",
            target_path="/procedure_steps",
            lesson_location="步骤一",
            issue="问题说明",
            evidence="教案中存在对应证据。",
            actionable_suggestion="按知识来源修改表述。",
            knowledge_source_refs=refs,
        )

    def test_fragment_id_citation_is_accepted(self) -> None:
        proposals = CritiqueProposalSet(
            items=[
                self._proposal(
                    RubricDimension.KNOWLEDGE_ACCURACY, ["fragment-16d8e49aeb9b"]
                )
            ]
        )

        # Regression: citing the task_context fragment by its real fragment id
        # used to be rejected because the guard only knew logical source ids.
        _validate_critic_batch(
            proposals,
            allowed_dimensions={RubricDimension.KNOWLEDGE_ACCURACY},
            known_sources=self._KNOWN,
        )

    def test_source_id_citation_is_accepted(self) -> None:
        proposals = CritiqueProposalSet(
            items=[
                self._proposal(RubricDimension.KNOWLEDGE_ACCURACY, ["task_context"])
            ]
        )

        _validate_critic_batch(
            proposals,
            allowed_dimensions={RubricDimension.KNOWLEDGE_ACCURACY},
            known_sources=self._KNOWN,
        )

    def test_fabricated_citation_is_still_rejected(self) -> None:
        proposals = CritiqueProposalSet(
            items=[
                self._proposal(
                    RubricDimension.KNOWLEDGE_ACCURACY, ["fragment-000000000000"]
                )
            ]
        )

        with self.assertRaisesRegex(ValueError, "cited unknown knowledge sources"):
            _validate_critic_batch(
                proposals,
                allowed_dimensions={RubricDimension.KNOWLEDGE_ACCURACY},
                known_sources=self._KNOWN,
            )

    def test_dimension_outside_role_boundary_is_rejected(self) -> None:
        proposals = CritiqueProposalSet(
            items=[
                self._proposal(RubricDimension.TEACHING_LOGIC, ["task_context"])
            ]
        )

        with self.assertRaisesRegex(ValueError, "dimension outside role boundary"):
            _validate_critic_batch(
                proposals,
                allowed_dimensions={RubricDimension.KNOWLEDGE_ACCURACY},
                known_sources=self._KNOWN,
            )


if __name__ == "__main__":
    unittest.main()
