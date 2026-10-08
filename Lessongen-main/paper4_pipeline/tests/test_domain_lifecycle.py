from __future__ import annotations

import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from support import make_critique, make_document, make_task, make_version

from paper4_pipeline.control.lifecycle import (
    actionable_critiques,
    apply_rewrite_outcome,
    apply_validation,
    detect_regressions,
    enforce_acceptance_cap,
    enforce_task_evidence_constraints,
    merge_critique_history,
    reopen_cap_deferred_for_validation,
    transition_critique,
    verify_rewrite,
)
from paper4_pipeline.domain.models import (
    CritiqueBatch,
    CritiqueItem,
    CritiqueStatus,
    LessonPlanDocument,
    RewriteChange,
    RewriteOutcome,
    RubricDimension,
    ValidationBatch,
    ValidationDecision,
    ValidationDecisionKind,
)
from paper4_pipeline.orchestration.state import assert_json_safe_state


class DomainJsonSafetyTests(unittest.TestCase):
    def test_domain_models_dump_to_json_safe_checkpoint_values(self) -> None:
        task = make_task()
        version = make_version("v0", 0, score=7.0, task=task)
        state = {
            "schema_version": "paper4-graph-state-v0.1",
            "task": task.model_dump(mode="json"),
            "versions": [version.model_dump(mode="json")],
        }

        assert_json_safe_state(state)
        encoded = json.dumps(state, ensure_ascii=False, allow_nan=False)

        self.assertIn("分数的意义", encoded)
        self.assertIsInstance(state["versions"][0]["created_at"], str)

    def test_json_safety_rejects_runtime_path_objects(self) -> None:
        with self.assertRaises(TypeError):
            assert_json_safe_state({"workspace_dir": Path("runtime-object")})


class CritiqueStateTests(unittest.TestCase):
    def test_non_proposed_critique_requires_transition_history(self) -> None:
        payload = make_critique("c-1").model_dump(mode="python")
        payload["status"] = CritiqueStatus.ACCEPTED

        with self.assertRaises(ValidationError):
            CritiqueItem.model_validate(payload)

    def test_illegal_state_transition_is_rejected_without_mutating_source(self) -> None:
        critique = make_critique("c-1")

        with self.assertRaisesRegex(ValueError, "illegal critique transition"):
            transition_critique(
                critique,
                CritiqueStatus.IMPLEMENTED,
                round_index=1,
                version_id="v1",
            )

        self.assertEqual(CritiqueStatus.PROPOSED, critique.status)
        self.assertEqual([], critique.history)

    def test_duplicate_history_ids_are_rejected_instead_of_silently_overwritten(self) -> None:
        critique = make_critique("c-duplicate")
        batch = CritiqueBatch(
            batch_id="batch-duplicate-guard",
            plan_version_id="v0",
            round_index=1,
            items=[critique],
        )

        with self.assertRaisesRegex(ValueError, "duplicate critique ids in critique history"):
            merge_critique_history([critique, critique], batch)


class ValidatorAndRewriterBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first = make_critique("c-accepted")
        self.second = make_critique("c-rejected")
        self.batch = CritiqueBatch(
            batch_id="critique-batch-1",
            plan_version_id="v0",
            round_index=1,
            items=[self.first, self.second],
        )

    @staticmethod
    def _decision(
        critique_id: str,
        kind: ValidationDecisionKind,
    ) -> ValidationDecision:
        accepted = kind == ValidationDecisionKind.ACCEPT
        return ValidationDecision(
            decision_id=f"decision-{critique_id}",
            critique_id=critique_id,
            decision=kind,
            grounded=accepted,
            relevant=accepted,
            actionable=accepted,
            reason="测试裁决",
        )

    def test_validator_must_cover_every_critique_exactly_once(self) -> None:
        incomplete = ValidationBatch(
            batch_id="validation-1",
            critique_batch_id=self.batch.batch_id,
            round_index=1,
            decisions=[
                self._decision("c-accepted", ValidationDecisionKind.ACCEPT)
            ],
        )

        with self.assertRaisesRegex(ValueError, "missing=.*c-rejected"):
            apply_validation(self.batch, incomplete)

    def test_only_accepted_critiques_are_actionable(self) -> None:
        validation = ValidationBatch(
            batch_id="validation-1",
            critique_batch_id=self.batch.batch_id,
            round_index=1,
            decisions=[
                self._decision("c-accepted", ValidationDecisionKind.ACCEPT),
                self._decision("c-rejected", ValidationDecisionKind.REJECT),
            ],
        )
        validated = apply_validation(self.batch, validation)

        actionable = actionable_critiques(validated)

        self.assertEqual(["c-accepted"], [item.critique_id for item in actionable])
        self.assertEqual(
            [CritiqueStatus.ACCEPTED, CritiqueStatus.REJECTED],
            [item.status for item in validated.items],
        )

    @staticmethod
    def _merge_decision(critique_id: str, canonical: str) -> ValidationDecision:
        return ValidationDecision(
            decision_id=f"decision-{critique_id}",
            critique_id=critique_id,
            decision=ValidationDecisionKind.MERGE,
            grounded=True,
            relevant=True,
            actionable=True,
            reason="重复意见合并",
            canonical_critique_id=canonical,
        )

    def test_merge_into_unknown_target_names_both_critique_ids(self) -> None:
        merged = make_critique("c-merged")
        batch = CritiqueBatch(
            batch_id="critique-batch-merge-unknown",
            plan_version_id="v0",
            round_index=1,
            items=[self.first, self.second, merged],
        )
        validation = ValidationBatch(
            batch_id="validation-1",
            critique_batch_id=batch.batch_id,
            round_index=1,
            decisions=[
                self._decision("c-accepted", ValidationDecisionKind.ACCEPT),
                self._decision("c-rejected", ValidationDecisionKind.REJECT),
                self._merge_decision("c-merged", "c-does-not-exist"),
            ],
        )

        with self.assertRaisesRegex(
            ValueError,
            r"critique 'c-merged' targets 'c-does-not-exist' for merge.*"
            r"Available IDs: \['c-accepted', 'c-merged', 'c-rejected'\]",
        ):
            apply_validation(batch, validation)

    def test_merge_into_rejected_target_names_both_critique_ids(self) -> None:
        merged = make_critique("c-merged")
        batch = CritiqueBatch(
            batch_id="critique-batch-merge-rejected",
            plan_version_id="v0",
            round_index=1,
            items=[self.first, self.second, merged],
        )
        validation = ValidationBatch(
            batch_id="validation-1",
            critique_batch_id=batch.batch_id,
            round_index=1,
            decisions=[
                self._decision("c-accepted", ValidationDecisionKind.ACCEPT),
                self._decision("c-rejected", ValidationDecisionKind.REJECT),
                self._merge_decision("c-merged", "c-rejected"),
            ],
        )

        with self.assertRaisesRegex(
            ValueError,
            r"critique 'c-merged' targets 'c-rejected' for merge.*"
            r"is 'reject'.*Current accepted IDs: \['c-accepted'\]",
        ):
            apply_validation(batch, validation)

    def test_missing_curriculum_source_cannot_be_accepted_for_rewrite(self) -> None:
        task = make_task().model_copy(update={"curriculum_standards": []})
        impossible = make_critique("c-no-standard").model_copy(
            update={
                "critic_profile_id": "alignment_critic_v0_1",
                "dimension": RubricDimension.CURRICULUM_ALIGNMENT,
                "issue_code": "obj-001-no-standard-ref",
                "target_path": "/learning_objectives",
                "lesson_location": "学习目标",
                "issue": "学习目标未关联课程标准，且任务没有提供课标。",
                "evidence": "curriculum_standards 为空。",
                "actionable_suggestion": "为每个目标补充 standard_refs 和课标条款。",
            }
        )
        batch = CritiqueBatch(
            batch_id="batch-empty-standards",
            plan_version_id="v0",
            round_index=1,
            items=[impossible],
        )
        accepted = self._decision("c-no-standard", ValidationDecisionKind.ACCEPT)

        guarded = enforce_task_evidence_constraints(batch, [accepted], task)
        validation = ValidationBatch(
            batch_id="validation-empty-standards",
            critique_batch_id=batch.batch_id,
            round_index=1,
            decisions=guarded,
        )
        validated = apply_validation(batch, validation)

        self.assertEqual(ValidationDecisionKind.REJECT, guarded[0].decision)
        self.assertFalse(guarded[0].actionable)
        self.assertTrue(guarded[0].conflict)
        self.assertIn("任务未提供课程标准", guarded[0].reason)
        self.assertEqual(CritiqueStatus.REJECTED, validated.items[0].status)
        self.assertEqual([], actionable_critiques(validated))

    def test_real_curriculum_source_keeps_alignment_accept_actionable(self) -> None:
        task = make_task()
        alignment = make_critique("c-with-standard").model_copy(
            update={
                "critic_profile_id": "alignment_critic_v0_1",
                "dimension": RubricDimension.CURRICULUM_ALIGNMENT,
                "issue_code": "objective_standard_ref_missing",
                "target_path": "/learning_objectives",
                "issue": "目标尚未引用已提供的课程标准。",
                "evidence": "任务含有课程标准。",
                "actionable_suggestion": "把已提供课标写入 standard_refs。",
            }
        )
        batch = CritiqueBatch(
            batch_id="batch-with-standards",
            plan_version_id="v0",
            round_index=1,
            items=[alignment],
        )
        accepted = self._decision("c-with-standard", ValidationDecisionKind.ACCEPT)

        guarded = enforce_task_evidence_constraints(batch, [accepted], task)

        self.assertEqual(ValidationDecisionKind.ACCEPT, guarded[0].decision)

    def test_rewriter_cannot_accept_an_identity_mutation_disguised_as_content_edit(self) -> None:
        task = make_task()
        impossible = make_critique("c-subject-mismatch").model_copy(update={
            "target_path": "/content_analysis",
            "issue": "原稿内容是英语，但任务科目填写为语文。",
            "actionable_suggestion": "将 metadata.subject 修改为初中英语。",
        })
        batch = CritiqueBatch(
            batch_id="batch-identity-mismatch",
            plan_version_id="v0",
            round_index=1,
            items=[impossible],
        )
        accepted = self._decision(
            "c-subject-mismatch", ValidationDecisionKind.ACCEPT,
        )

        guarded = enforce_task_evidence_constraints(batch, [accepted], task)

        self.assertEqual(ValidationDecisionKind.REJECT, guarded[0].decision)
        self.assertFalse(guarded[0].actionable)
        self.assertTrue(guarded[0].conflict)
        self.assertIn("任务身份", guarded[0].reason)

    def test_merge_into_unavailable_evidence_canonical_is_also_rejected(self) -> None:
        task = make_task().model_copy(update={"curriculum_standards": []})
        canonical = make_critique("c-canonical").model_copy(
            update={
                "critic_profile_id": "alignment_critic_v0_1",
                "dimension": RubricDimension.CURRICULUM_ALIGNMENT,
                "issue_code": "ALIGN-01",
                "target_path": "/learning_objectives",
                "issue": "未引用课标。",
                "evidence": "课程标准为空。",
                "actionable_suggestion": "添加课程标准占位符和 standard_refs。",
            }
        )
        duplicate = canonical.model_copy(
            update={"critique_id": "c-duplicate", "issue_code": "ALIGN-DUP"}
        )
        batch = CritiqueBatch(
            batch_id="batch-empty-standards-merge",
            plan_version_id="v0",
            round_index=1,
            items=[canonical, duplicate],
        )
        accepted = self._decision("c-canonical", ValidationDecisionKind.ACCEPT)
        merged = ValidationDecision(
            decision_id="decision-c-duplicate",
            critique_id="c-duplicate",
            decision=ValidationDecisionKind.MERGE,
            canonical_critique_id="c-canonical",
            grounded=True,
            relevant=True,
            actionable=True,
            reason="同一问题。",
        )

        guarded = enforce_task_evidence_constraints(batch, [accepted, merged], task)

        self.assertEqual(
            [ValidationDecisionKind.REJECT, ValidationDecisionKind.REJECT],
            [item.decision for item in guarded],
        )
        apply_validation(
            batch,
            ValidationBatch(
                batch_id="validation-empty-standards-merge",
                critique_batch_id=batch.batch_id,
                round_index=1,
                decisions=guarded,
            ),
        )

    def test_rewrite_mapping_cannot_include_rejected_critique(self) -> None:
        validation = ValidationBatch(
            batch_id="validation-1",
            critique_batch_id=self.batch.batch_id,
            round_index=1,
            decisions=[
                self._decision("c-accepted", ValidationDecisionKind.ACCEPT),
                self._decision("c-rejected", ValidationDecisionKind.REJECT),
            ],
        )
        validated = apply_validation(self.batch, validation)
        outcome = RewriteOutcome(
            document=make_version("v0", 0, score=7.0).document,
            changes=[
                RewriteChange(
                    critique_id="c-rejected",
                    target_path="/differentiation",
                    lesson_location="差异化支持",
                    before_summary="原字段为空",
                    after_summary="错误地执行了被拒绝意见",
                    implementation_status="implemented",
                )
            ],
        )

        with self.assertRaisesRegex(ValueError, "invalid rewrite mapping"):
            apply_rewrite_outcome(
                validated,
                outcome,
                round_index=1,
                output_version_id="v1",
            )

    def test_unresolved_must_use_the_dedicated_id_list(self) -> None:
        with self.assertRaises(ValidationError):
            RewriteChange(
                critique_id="c-accepted",
                target_path="/differentiation",
                lesson_location="差异化支持",
                before_summary="原内容",
                after_summary="未能修改",
                implementation_status="unresolved",
            )

    def test_unresolved_ids_must_be_unique(self) -> None:
        with self.assertRaisesRegex(ValidationError, "duplicate unresolved critique IDs"):
            RewriteOutcome(
                document=make_document(),
                unresolved_critique_ids=["c-accepted", "c-accepted"],
            )


class AcceptanceCapTests(unittest.TestCase):
    """The Validator prompt's "at most five accepts per round" is structural."""

    @staticmethod
    def _decision(
        critique_id: str,
        kind: ValidationDecisionKind,
        *,
        priority: int = 0,
        canonical: str = "",
    ) -> ValidationDecision:
        return ValidationDecision(
            decision_id=f"decision-{critique_id}",
            critique_id=critique_id,
            decision=kind,
            grounded=True,
            relevant=True,
            actionable=kind == ValidationDecisionKind.ACCEPT,
            conflict=False,
            priority=priority,
            reason="测试裁决",
            canonical_critique_id=canonical,
        )

    def test_surplus_accepts_are_deferred_by_priority(self) -> None:
        decisions = [
            self._decision("c-1", ValidationDecisionKind.ACCEPT, priority=90),
            self._decision("c-2", ValidationDecisionKind.ACCEPT, priority=40),
            self._decision("c-3", ValidationDecisionKind.ACCEPT, priority=75),
            self._decision("c-4", ValidationDecisionKind.ACCEPT, priority=65),
            self._decision("c-5", ValidationDecisionKind.ACCEPT, priority=60),
            self._decision("c-6", ValidationDecisionKind.ACCEPT, priority=60),
        ]

        capped = enforce_acceptance_cap(decisions)

        by_id = {decision.critique_id: decision for decision in capped}
        self.assertEqual(6, len(capped))
        accepted = {
            item.critique_id
            for item in capped
            if item.decision == ValidationDecisionKind.ACCEPT
        }
        self.assertEqual({"c-1", "c-3", "c-4", "c-5", "c-6"}, accepted)
        self.assertEqual(ValidationDecisionKind.DEFER, by_id["c-2"].decision)
        self.assertEqual("", by_id["c-2"].canonical_critique_id)
        self.assertTrue(by_id["c-2"].reason)

    def test_blocking_rule_critique_is_kept_ahead_of_a_higher_soft_priority(self) -> None:
        decisions = [
            self._decision("soft", ValidationDecisionKind.ACCEPT, priority=100),
            self._decision("required", ValidationDecisionKind.ACCEPT, priority=20),
        ]

        capped = enforce_acceptance_cap(
            decisions,
            max_accepts=1,
            priority_critique_ids={"required"},
        )

        by_id = {item.critique_id: item for item in capped}
        self.assertEqual(ValidationDecisionKind.ACCEPT, by_id["required"].decision)
        self.assertEqual(ValidationDecisionKind.DEFER, by_id["soft"].decision)

    def test_cap_is_noop_below_the_limit(self) -> None:
        decisions = [
            self._decision("c-1", ValidationDecisionKind.ACCEPT, priority=50),
            self._decision("c-2", ValidationDecisionKind.ACCEPT, priority=40),
            self._decision("c-3", ValidationDecisionKind.REJECT),
        ]

        capped = enforce_acceptance_cap(decisions)

        self.assertEqual(decisions, capped)
        kinds = {item.decision for item in capped}
        self.assertNotIn(ValidationDecisionKind.DEFER, kinds)

    def test_merge_anchor_is_kept_and_merge_follows_its_canonical(self) -> None:
        decisions = [
            self._decision("c-a", ValidationDecisionKind.ACCEPT, priority=10),
            self._decision("c-b", ValidationDecisionKind.ACCEPT, priority=100),
            self._decision("c-c", ValidationDecisionKind.ACCEPT, priority=90),
            self._decision(
                "c-m",
                ValidationDecisionKind.MERGE,
                canonical="c-a",
            ),
        ]

        capped = enforce_acceptance_cap(decisions, max_accepts=2)

        by_id = {decision.critique_id: decision for decision in capped}
        # The protected merge anchor survives even below its lower priority.
        self.assertEqual(ValidationDecisionKind.ACCEPT, by_id["c-a"].decision)
        self.assertEqual(ValidationDecisionKind.ACCEPT, by_id["c-b"].decision)
        self.assertEqual(ValidationDecisionKind.DEFER, by_id["c-c"].decision)
        self.assertEqual(ValidationDecisionKind.MERGE, by_id["c-m"].decision)

    def test_merge_is_deferred_when_its_canonical_is_capped(self) -> None:
        decisions = [
            self._decision("c-a", ValidationDecisionKind.ACCEPT, priority=5),
            self._decision("c-b", ValidationDecisionKind.ACCEPT, priority=100),
            self._decision(
                "m-a",
                ValidationDecisionKind.MERGE,
                canonical="c-a",
            ),
            self._decision(
                "m-b",
                ValidationDecisionKind.MERGE,
                canonical="c-b",
            ),
        ]

        capped = enforce_acceptance_cap(decisions, max_accepts=1)

        by_id = {decision.critique_id: decision for decision in capped}
        self.assertEqual(ValidationDecisionKind.ACCEPT, by_id["c-b"].decision)
        self.assertEqual(ValidationDecisionKind.DEFER, by_id["c-a"].decision)
        self.assertEqual(ValidationDecisionKind.MERGE, by_id["m-b"].decision)
        self.assertEqual(ValidationDecisionKind.DEFER, by_id["m-a"].decision)
        self.assertEqual("", by_id["m-a"].canonical_critique_id)


class RewriteVerificationTests(unittest.TestCase):
    """Deterministic semantic verification must never punish an implemented
    rewrite just because its target path cannot be exactly located."""

    @staticmethod
    def _critique(critique_id: str, issue_code: str, target_path: str) -> CritiqueItem:
        payload = make_critique(critique_id).model_dump(mode="python")
        payload["issue_code"] = issue_code
        payload["target_path"] = target_path
        return CritiqueItem.model_validate(payload)

    @classmethod
    def _implemented(
        cls,
        critique_id: str,
        issue_code: str,
        target_path: str,
    ) -> CritiqueItem:
        proposed = cls._critique(critique_id, issue_code, target_path)
        accepted = transition_critique(
            proposed,
            CritiqueStatus.ACCEPTED,
            round_index=1,
            note="accepted",
        )
        return transition_critique(
            accepted,
            CritiqueStatus.IMPLEMENTED,
            round_index=1,
            version_id="v1",
            note="implemented",
        )

    @staticmethod
    def _batch(*items: CritiqueItem) -> CritiqueBatch:
        return CritiqueBatch(
            batch_id="batch-v1",
            plan_version_id="v0",
            round_index=1,
            items=list(items),
        )

    def test_unlocatable_implemented_fix_is_not_downgraded(self) -> None:
        task = make_task()
        # Only 3 procedure steps exist; index 5 cannot be addressed.  This
        # mirrors the live run where a critic emitted "/procedure_steps/5".
        document = make_document(task, high_quality=True)
        item = self._implemented(
            "c-step",
            "step_no_assessment",
            "/procedure_steps/5/assessment",
        )

        verified = verify_rewrite(self._batch(item), document, 1, "v1")

        self.assertEqual(CritiqueStatus.IMPLEMENTED, verified.items[0].status)

    def test_located_and_filled_fix_is_verified(self) -> None:
        task = make_task()
        document = make_document(task, high_quality=True)
        item = self._implemented(
            "c-obj",
            "objective_no_evidence",
            "/learning_objectives/0",
        )

        verified = verify_rewrite(self._batch(item), document, 1, "v1")

        self.assertEqual(CritiqueStatus.VERIFIED_FIXED, verified.items[0].status)

    def test_located_still_failing_is_downgraded_to_unresolved(self) -> None:
        task = make_task()
        document = make_document(task)  # differentiation and objective evidence empty
        item = self._implemented(
            "c-diff",
            "missing_differentiation",
            "/differentiation",
        )

        verified = verify_rewrite(self._batch(item), document, 1, "v1")

        self.assertEqual(CritiqueStatus.UNRESOLVED, verified.items[0].status)

    def test_unlocatable_verified_fix_is_not_reopened_as_regression(self) -> None:
        task = make_task()
        document = make_document(task, high_quality=True)
        verified_fixed = transition_critique(
            self._implemented(
                "c-step",
                "step_no_assessment",
                "/procedure_steps/5/assessment",
            ),
            CritiqueStatus.VERIFIED_FIXED,
            round_index=1,
            version_id="v1",
            note="contract verified",
        )

        history = detect_regressions([verified_fixed], document, 1, "v2")

        self.assertEqual(CritiqueStatus.VERIFIED_FIXED, history[0].status)

    def test_positively_reconfirmed_failure_is_regression(self) -> None:
        task = make_task()
        regressed_document = make_document(task)  # differentiation is empty again
        verified_fixed = transition_critique(
            self._implemented(
                "c-diff",
                "missing_differentiation",
                "/differentiation",
            ),
            CritiqueStatus.VERIFIED_FIXED,
            round_index=1,
            version_id="v1",
            note="deterministic semantic verification",
        )

        history = detect_regressions([verified_fixed], regressed_document, 1, "v2")

        self.assertEqual(CritiqueStatus.REGRESSION, history[0].status)


class PresenceProbeVerificationTests(unittest.TestCase):
    """Live critics rarely emit the four legacy deterministic codes; they emit
    free-form codes for real content gaps (e.g. a still-empty top-level
    section).  The presence probe catches an IMPLEMENTED claim that left such a
    field empty -- and only that.  It never certifies a fix (content presence
    does not prove a critique was satisfied), so VERIFIED_FIXED stays
    deterministic-only."""

    @staticmethod
    def _implemented(
        critique_id: str,
        *,
        issue_code: str,
        target_path: str,
        issue: str,
        evidence: str = "",
    ) -> CritiqueItem:
        payload = make_critique(critique_id).model_dump(mode="python")
        payload["issue_code"] = issue_code
        payload["target_path"] = target_path
        payload["issue"] = issue
        payload["evidence"] = evidence or issue
        proposed = CritiqueItem.model_validate(payload)
        accepted = transition_critique(
            proposed,
            CritiqueStatus.ACCEPTED,
            round_index=1,
            note="accepted",
        )
        return transition_critique(
            accepted,
            CritiqueStatus.IMPLEMENTED,
            round_index=1,
            version_id="v1",
            note="implemented",
        )

    @staticmethod
    def _verify(item: CritiqueItem, document: LessonPlanDocument) -> CritiqueStatus:
        batch = CritiqueBatch(
            batch_id="batch-probe",
            plan_version_id="v0",
            round_index=1,
            items=[item],
        )
        verified = verify_rewrite(batch, document, 1, "v1")
        return verified.items[0].status

    def test_empty_field_claimed_implemented_is_unresolved(self) -> None:
        task = make_task()
        document = make_document(task, high_quality=True)
        document.homework = ""  # rewrite claimed a fix that is not there
        item = self._implemented(
            "c-hw",
            issue_code="homework_not_assigned",
            target_path="/homework",
            issue="homework 为空，未布置任何课后作业。",
            evidence="homework 字段仍为空。",
        )

        status = self._verify(item, document)

        self.assertEqual(CritiqueStatus.UNRESOLVED, status)

    def test_empty_list_field_claimed_implemented_is_unresolved(self) -> None:
        task = make_task()
        document = make_document(task, high_quality=True)
        document.curriculum_standards = []
        item = self._implemented(
            "c-cs",
            issue_code="curriculum_standards_missing",
            target_path="/curriculum_standards",
            issue="curriculum_standards 为空数组，缺少课标依据。",
            evidence="curriculum_standards: []。",
        )

        status = self._verify(item, document)

        self.assertEqual(CritiqueStatus.UNRESOLVED, status)

    def test_field_now_present_stays_implemented(self) -> None:
        task = make_task()
        document = make_document(task, high_quality=True)  # homework is filled
        item = self._implemented(
            "c-hw",
            issue_code="homework_not_assigned",
            target_path="/homework",
            issue="homework 为空，未布置任何课后作业。",
        )

        status = self._verify(item, document)

        self.assertEqual(CritiqueStatus.IMPLEMENTED, status)

    def test_empty_field_without_absence_marker_is_not_probed(self) -> None:
        task = make_task()
        document = make_document(task, high_quality=True)
        document.homework = ""  # empty, but the critique is not about absence
        item = self._implemented(
            "c-hw",
            issue_code="homework_depth_variation",
            target_path="/homework",
            issue="homework 的难度梯度可进一步分层设计。",
            evidence="homework 目前只有单一题型。",
        )

        status = self._verify(item, document)

        # No absence claim -> no downgrade.  Independent review owns the issue.
        self.assertEqual(CritiqueStatus.IMPLEMENTED, status)

    def test_nested_path_is_not_probed(self) -> None:
        # target_path is schema-restricted to the document's top-level fields,
        # so an "unknown root" cannot occur; but a nested path addresses an
        # element, not the field itself, and must never be reduced to a whole
        # field being empty.
        task = make_task()
        document = make_document(task, high_quality=True)
        document.homework = ""
        nested = self._implemented(
            "c-nested",
            issue_code="homework_not_assigned",
            target_path="/homework/0",
            issue="homework 为空。",
        )

        self.assertEqual(CritiqueStatus.IMPLEMENTED, self._verify(nested, document))


class CapDeferReopeningTests(unittest.TestCase):
    """DEFER was terminal: no producer ever transitioned DEFERRED -> REOPENED,
    so the structural acceptance cap silently parked genuinely accepted
    opinions forever.  Reactivation deterministically replays those opinions
    once each, oldest first, bounded per rewrite round, and never touches a
    critique the Validator itself deferred."""

    _CAP_NOTE = "每轮至多接受 5 条最高杠杆意见；其余经核验的真实意见顺延至后续轮次（defer），并非否定其价值。"

    @classmethod
    def _deferred(
        cls,
        critique_id: str,
        *,
        introduced_in_round: int,
        note: str,
    ) -> CritiqueItem:
        payload = make_critique(critique_id).model_dump(mode="python")
        payload["introduced_in_round"] = introduced_in_round
        proposed = CritiqueItem.model_validate(payload)
        return transition_critique(
            proposed,
            CritiqueStatus.DEFERRED,
            round_index=1,
            note=note,
        )

    def test_cap_deferred_items_are_reopened_oldest_first(self) -> None:
        history = [
            self._deferred(
                "c-old", introduced_in_round=1, note=self._CAP_NOTE
            ),
            self._deferred(
                "c-new", introduced_in_round=2, note=self._CAP_NOTE
            ),
            self._deferred(
                "c-genuine",
                introduced_in_round=2,
                note="该意见与当前学习目标无直接冲突，暂缓处理。",
            ),
        ]

        updated, reopened = reopen_cap_deferred_for_validation(
            history, round_index=3, version_id="v3"
        )

        self.assertEqual(
            ["c-old", "c-new"],
            [item.critique_id for item in reopened],
        )
        by_id = {item.critique_id: item for item in updated}
        self.assertEqual(CritiqueStatus.REOPENED, by_id["c-old"].status)
        self.assertEqual(CritiqueStatus.REOPENED, by_id["c-new"].status)
        # A genuine Validator DEFER is never auto-revived.
        self.assertEqual(CritiqueStatus.DEFERRED, by_id["c-genuine"].status)

    def test_reopening_is_bounded_and_idempotent(self) -> None:
        history = [
            self._deferred("c-1", introduced_in_round=1, note=self._CAP_NOTE),
            self._deferred("c-2", introduced_in_round=1, note=self._CAP_NOTE),
        ]

        updated, first = reopen_cap_deferred_for_validation(
            history, round_index=2, version_id="v2", per_round=1
        )
        self.assertEqual(["c-1"], [item.critique_id for item in first])
        self.assertEqual(
            CritiqueStatus.DEFERRED,
            next(item for item in updated if item.critique_id == "c-2").status,
        )

        updated, second = reopen_cap_deferred_for_validation(
            updated, round_index=3, version_id="v3", per_round=1
        )
        self.assertEqual(["c-2"], [item.critique_id for item in second])

        updated, third = reopen_cap_deferred_for_validation(
            updated, round_index=4, version_id="v4"
        )
        # Every item now carries a REOPENED transition; none is re-eligible.
        self.assertEqual([], third)
        self.assertTrue(
            all(item.status == CritiqueStatus.REOPENED for item in updated)
        )

    def test_reopened_item_awaits_validator_decision(self) -> None:
        history = [self._deferred("c-1", introduced_in_round=1, note=self._CAP_NOTE)]

        updated, reopened = reopen_cap_deferred_for_validation(
            history, round_index=2, version_id="v2"
        )

        item = updated[0]
        statuses = [transition.to_status for transition in item.history]
        self.assertEqual(
            [
                CritiqueStatus.DEFERRED,
                CritiqueStatus.REOPENED,
            ],
            statuses,
        )
        self.assertEqual("c-1", reopened[0].critique_id)

    def test_same_round_cap_defer_is_not_reopened(self) -> None:
        history = [self._deferred("c-1", introduced_in_round=1, note=self._CAP_NOTE)]

        updated, reopened = reopen_cap_deferred_for_validation(
            history, round_index=1, version_id="v0"
        )

        self.assertEqual([], reopened)
        self.assertEqual(CritiqueStatus.DEFERRED, updated[0].status)

    def test_excluded_id_is_not_reopened_or_mutated(self) -> None:
        history = [self._deferred("c-1", introduced_in_round=1, note=self._CAP_NOTE)]

        updated, reopened = reopen_cap_deferred_for_validation(
            history,
            round_index=2,
            version_id="v1",
            exclude_ids={"c-1"},
        )

        self.assertEqual([], reopened)
        self.assertEqual(CritiqueStatus.DEFERRED, updated[0].status)


class ReopenedMergeTests(unittest.TestCase):
    """A reopened cap-deferred opinion can be superseded by a fresher proposal.

    Round-N critics may re-raise an issue that round N-1 already parked behind
    the acceptance cap and that was then reopened for this batch.  The
    Validator is free to keep the fresh proposal as canonical and MERGE the
    older reopened item into it.  reopened -> merged must therefore be legal
    (regression: it was once absent and crashed round-2 runs with
    ``ValueError: illegal critique transition: reopened -> merged``)."""

    _CAP_NOTE = "每轮至多接受 5 条最高杠杆意见；其余经核验的真实意见顺延至后续轮次（defer），并非否定其价值。"

    def _reopened(self, critique_id: str) -> CritiqueItem:
        deferred = transition_critique(
            make_critique(critique_id),
            CritiqueStatus.DEFERRED,
            round_index=1,
            note=self._CAP_NOTE,
        )
        _, reopened = reopen_cap_deferred_for_validation(
            [deferred], round_index=2, version_id="v1"
        )
        self.assertEqual(1, len(reopened))
        return reopened[0]

    def test_reopened_transition_table_allows_merge(self) -> None:
        reopened = self._reopened("c-old")

        merged = transition_critique(
            reopened,
            CritiqueStatus.MERGED,
            round_index=2,
            version_id="v1",
            note="被更完整的新提案吸收",
        )

        self.assertEqual(CritiqueStatus.MERGED, merged.status)
        self.assertEqual(CritiqueStatus.MERGED, merged.history[-1].to_status)

    def test_reopened_item_merges_into_fresh_round2_canonical(self) -> None:
        reopened = self._reopened("c-old")
        fresh = make_critique("c-fresh")
        batch = CritiqueBatch(
            batch_id="critique-batch-r2",
            plan_version_id="v1",
            round_index=2,
            items=[fresh, reopened],
        )
        validation = ValidationBatch(
            batch_id="validation-r2",
            critique_batch_id=batch.batch_id,
            round_index=2,
            decisions=[
                ValidationDecision(
                    decision_id="decision-c-fresh",
                    critique_id="c-fresh",
                    decision=ValidationDecisionKind.ACCEPT,
                    grounded=True,
                    relevant=True,
                    actionable=True,
                    reason="新提案表述更完整，作为 canonical 保留。",
                ),
                ValidationDecision(
                    decision_id="decision-c-old",
                    critique_id="c-old",
                    decision=ValidationDecisionKind.MERGE,
                    canonical_critique_id="c-fresh",
                    grounded=True,
                    relevant=True,
                    actionable=True,
                    reason="与 c-fresh 重复，合并进新 canonical。",
                ),
            ],
        )

        validated = apply_validation(batch, validation)
        by_id = {item.critique_id: item for item in validated.items}

        # The older reopened item is folded into the fresh accepted canonical…
        self.assertEqual(CritiqueStatus.MERGED, by_id["c-old"].status)
        self.assertEqual("c-fresh", by_id["c-old"].canonical_critique_id)
        # …so only the fresh canonical reaches the Rewriter.
        self.assertEqual(
            ["c-fresh"], [item.critique_id for item in actionable_critiques(validated)]
        )
        # History stays append-only: DEFERRED -> REOPENED -> MERGED.
        self.assertEqual(
            [
                CritiqueStatus.DEFERRED,
                CritiqueStatus.REOPENED,
                CritiqueStatus.MERGED,
            ],
            [transition.to_status for transition in by_id["c-old"].history],
        )

    def test_reopened_item_can_still_be_canonical_for_fresh_duplicate(self) -> None:
        """The opposite merge direction (keep the reopened item, fold the fresh
        proposal into it) remains legal and worked before the fix."""
        reopened = self._reopened("c-old")
        fresh = make_critique("c-fresh")
        batch = CritiqueBatch(
            batch_id="critique-batch-r2b",
            plan_version_id="v1",
            round_index=2,
            items=[fresh, reopened],
        )
        validation = ValidationBatch(
            batch_id="validation-r2b",
            critique_batch_id=batch.batch_id,
            round_index=2,
            decisions=[
                ValidationDecision(
                    decision_id="decision-c-old",
                    critique_id="c-old",
                    decision=ValidationDecisionKind.ACCEPT,
                    grounded=True,
                    relevant=True,
                    actionable=True,
                    reason="旧意见保留历史，作为 canonical。",
                ),
                ValidationDecision(
                    decision_id="decision-c-fresh",
                    critique_id="c-fresh",
                    decision=ValidationDecisionKind.MERGE,
                    canonical_critique_id="c-old",
                    grounded=True,
                    relevant=True,
                    actionable=True,
                    reason="与 c-old 重复。",
                ),
            ],
        )

        validated = apply_validation(batch, validation)
        by_id = {item.critique_id: item for item in validated.items}

        self.assertEqual(CritiqueStatus.ACCEPTED, by_id["c-old"].status)
        self.assertEqual(CritiqueStatus.MERGED, by_id["c-fresh"].status)
        self.assertEqual(
            ["c-old"], [item.critique_id for item in actionable_critiques(validated)]
        )


if __name__ == "__main__":
    unittest.main()
