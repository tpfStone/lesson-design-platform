from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from support import make_task, make_version

from paper4_pipeline.domain.models import PipelineResult, RunStatus, StopReason, TaskMode
from paper4_pipeline.control.optimization import optimization_summary
from paper4_pipeline.control.versioning import document_hash
from paper4_pipeline.exporters.manifest import export_artifacts


class ArtifactExporterTests(unittest.TestCase):
    def test_failed_optimization_keeps_recovery_process_without_success_manifest(self) -> None:
        task = make_task()
        baseline = make_version("v0", 0, score=6.5, task=task)
        result = PipelineResult(
            run_id="failed-optimization", task_id=task.task_id,
            task_mode=TaskMode.OPTIMIZE, experiment_id="unit", method_id="unit",
            status=RunStatus.FAILED, stop_reason=StopReason.REWRITE_FAILED,
            best_version_id="v0", last_version_id="v0", versions=[baseline],
        )
        self.assertEqual("rewrite_failed", optimization_summary(result)["outcome"])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            export_artifacts(result, folder, include_docx=True)
            self.assertTrue((folder / "optimization_report.json").is_file())
            self.assertTrue((folder / "optimization_report.md").is_file())
            self.assertFalse((folder / "manifest.json").exists())
            self.assertFalse((folder / "best_lesson_plan.docx").exists())

    def test_optimization_reports_no_change_even_when_same_plan_scores_higher(self) -> None:
        task = make_task()
        baseline = make_version("v0", 0, score=8.1, task=task)
        same_content = make_version("v1", 1, score=8.2, task=task,
                                    parent_version_id="v0")
        result = PipelineResult(
            run_id="same-plan", task_id=task.task_id, task_mode=TaskMode.OPTIMIZE,
            experiment_id="unit", method_id="unit", status=RunStatus.COMPLETED,
            stop_reason=StopReason.MAX_ROUNDS, best_version_id="v1",
            last_version_id="v1", versions=[baseline, same_content],
        )
        summary = optimization_summary(result)
        self.assertFalse(summary["content_changed"])
        self.assertIsNone(summary["score_delta"])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            exported = export_artifacts(result, folder, include_docx=False)
            best = json.loads((folder / "best_lesson_plan.json").read_text(encoding="utf-8"))
            report = json.loads((folder / "optimization_report.json").read_text(encoding="utf-8"))
            md = (folder / "best_lesson_plan.md").read_text(encoding="utf-8")
            self.assertFalse(best["optimization"]["content_changed"])
            self.assertEqual([], report["summary"]["changed_sections"])
            self.assertIn("本次优化核验", md)
            self.assertIn("没有实际内容变化", (folder / "optimization_report.md").read_text(encoding="utf-8"))
            self.assertIn("optimization-report-json", {
                item.artifact_id for item in exported.artifacts.artifacts
            })

    def test_optimization_report_contains_real_before_after_content(self) -> None:
        task = make_task()
        baseline = make_version("v0", 0, score=7.5, task=task)
        candidate = make_version("v1", 1, score=8.0, task=task,
                                 parent_version_id="v0")
        changed_doc = candidate.document.model_copy(update={
            "content_analysis": "新增了可直接使用的学科材料与误概念处理"
        })
        candidate = candidate.model_copy(update={
            "document": changed_doc, "document_hash": document_hash(changed_doc)
        })
        result = PipelineResult(
            run_id="changed-plan", task_id=task.task_id, task_mode=TaskMode.OPTIMIZE,
            experiment_id="unit", method_id="unit", status=RunStatus.COMPLETED,
            stop_reason=StopReason.QUALITY_PASSED, best_version_id="v1",
            last_version_id="v1", versions=[baseline, candidate],
        )
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            export_artifacts(result, folder, include_docx=False)
            report = json.loads((folder / "optimization_report.json").read_text(encoding="utf-8"))
            change = next(item for item in report["summary"]["changed_sections"]
                          if item["field"] == "content_analysis")
            self.assertEqual(baseline.document.content_analysis, change["before"])
            self.assertEqual(changed_doc.content_analysis, change["after"])
            self.assertTrue(report["summary"]["content_changed"])

    def test_unselected_real_revision_is_downloadable_as_review_candidate(self) -> None:
        task = make_task()
        baseline = make_version("v0", 0, score=7.5, task=task)
        candidate = make_version("v1", 1, score=7.4, task=task,
                                 parent_version_id="v0")
        changed_doc = candidate.document.model_copy(update={
            "content_analysis": baseline.document.content_analysis + "。补充具体学习任务。"
        })
        candidate = candidate.model_copy(update={
            "document": changed_doc, "document_hash": document_hash(changed_doc)
        })
        result = PipelineResult(
            run_id="candidate-plan", task_id=task.task_id, task_mode=TaskMode.OPTIMIZE,
            experiment_id="unit", method_id="unit", status=RunStatus.NEEDS_HUMAN,
            stop_reason=StopReason.MAX_ROUNDS, best_version_id="v0",
            last_version_id="v1", versions=[baseline, candidate],
        )
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            exported = export_artifacts(result, folder, include_docx=True)
            summary = optimization_summary(exported)
            self.assertFalse(summary["content_changed"])
            self.assertEqual("v1", summary["unselected_candidate_version_id"])
            self.assertEqual("content_analysis", summary["unselected_candidate_changed_sections"][0]["field"])
            self.assertTrue((folder / "revised_candidate.docx").is_file())
            self.assertIn("revised-candidate-docx", {
                item.artifact_id for item in exported.artifacts.artifacts
            })

    def test_exports_a_completed_domain_result_without_calling_a_model(self) -> None:
        task = make_task()
        version = make_version("v0", 0, score=8.5, task=task)
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "artifact-contract-run"
            run_dir.mkdir(parents=True)
            trace = run_dir / "trace.jsonl"
            trace.write_text('{"event_type":"unit_fixture"}\n', encoding="utf-8")
            result = PipelineResult(
                run_id="artifact-contract-run",
                task_id=task.task_id,
                experiment_id="unit-export",
                method_id="hand-built-domain-fixture",
                status=RunStatus.COMPLETED,
                stop_reason=StopReason.QUALITY_PASSED,
                best_version_id="v0",
                last_version_id="v0",
                versions=[version],
                trace_path=str(trace),
            )

            exported = export_artifacts(result, run_dir, include_docx=False)
            json_path = run_dir / "best_lesson_plan.json"
            markdown_path = run_dir / "best_lesson_plan.md"
            manifest_path = run_dir / "manifest.json"
            run_result_path = run_dir / "run_result.json"

            self.assertTrue(json_path.is_file())
            self.assertTrue(markdown_path.is_file())
            self.assertTrue(manifest_path.is_file())
            self.assertTrue(run_result_path.is_file())
            self.assertFalse((run_dir / "best_lesson_plan.docx").exists())

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual("v0", payload["best_version_id"])
        self.assertEqual("分数的意义", payload["lesson_plan"]["metadata"]["topic"])
        self.assertIn("# 分数的意义教学设计", markdown)
        self.assertIn("最佳版本 `v0`", markdown)
        self.assertEqual("v0", manifest["best_version_id"])
        self.assertEqual(
            {"json", "markdown", "trace"},
            {item["format"] for item in manifest["artifacts"]},
        )
        self.assertIsNotNone(exported.artifacts)

    def test_failed_result_with_versions_exports_recovery_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "failed-run"
            task = make_task()
            version = make_version("v0", 0, score=6.5, task=task)
            result = PipelineResult(
                run_id="failed-run",
                task_id=task.task_id,
                experiment_id="unit-export",
                method_id="live-contract",
                status=RunStatus.FAILED,
                stop_reason=StopReason.REWRITE_FAILED,
                best_version_id="v0",
                last_version_id="v0",
                versions=[version],
                errors=["rewriter failed after 3 attempts"],
            )
            exported = export_artifacts(result, run_dir)

            # A late failure yields explicitly marked recovery files, never a
            # misleading best-plan name or success manifest.
            self.assertTrue((run_dir / "run_result.json").is_file())
            recovery_json = run_dir / "recovery_lesson_plan.json"
            recovery_md = run_dir / "recovery_lesson_plan.md"
            self.assertTrue(recovery_json.is_file())
            self.assertTrue(recovery_md.is_file())
            self.assertFalse((run_dir / "best_lesson_plan.json").exists())
            self.assertFalse((run_dir / "best_lesson_plan.md").exists())
            self.assertFalse((run_dir / "best_lesson_plan.docx").exists())
            self.assertFalse((run_dir / "manifest.json").exists())
            self.assertIsNone(exported.artifacts)
            payload = json.loads(recovery_json.read_text(encoding="utf-8"))
            markdown = recovery_md.read_text(encoding="utf-8")
            self.assertEqual("failed", payload["run_status"])
            self.assertTrue(payload["recovery_only"])
            self.assertIn("失败运行的恢复草稿", markdown)

    def test_needs_human_result_exports_best_with_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "needs-human-run"
            task = make_task()
            version = make_version("v0", 0, score=6.8, task=task)
            result = PipelineResult(
                run_id="needs-human-run",
                task_id=task.task_id,
                experiment_id="unit-export",
                method_id="live-contract",
                status=RunStatus.NEEDS_HUMAN,
                stop_reason=StopReason.PLATEAU,
                best_version_id="v0",
                last_version_id="v0",
                versions=[version],
            )
            exported = export_artifacts(result, run_dir)

            self.assertTrue((run_dir / "best_lesson_plan.json").is_file())
            self.assertTrue((run_dir / "manifest.json").is_file())
            self.assertIsNotNone(exported.artifacts)


class PipelineResultInvariantTests(unittest.TestCase):
    """The FAILED stop-reason whitelist that the graph's abort paths rely on.

    ``_finalize`` maps both REWRITE_FAILED (aborted rewrite) and ROLLBACK
    (regression guard, no rollback node in v0.1) to RunStatus.FAILED.  These
    must be representable as a PipelineResult, while success reasons must not
    be smuggled under a FAILED status.
    """

    def test_failed_result_accepts_regression_guard_stop_reason(self) -> None:
        task = make_task()
        version = make_version("v0", 0, score=6.0, task=task)
        result = PipelineResult(
            run_id="rollback-guard",
            task_id=task.task_id,
            experiment_id="unit-export",
            method_id="live-contract",
            status=RunStatus.FAILED,
            stop_reason=StopReason.REGRESSION_GUARD,
            best_version_id="v0",
            last_version_id="v0",
            versions=[version],
            errors=["regression detected; stopped for human review"],
        )

        self.assertEqual(RunStatus.FAILED, result.status)

    def test_failed_result_rejects_success_stop_reason(self) -> None:
        task = make_task()
        version = make_version("v0", 0, score=6.0, task=task)
        with self.assertRaises(ValueError):
            PipelineResult(
                run_id="wrong-reason",
                task_id=task.task_id,
                experiment_id="unit-export",
                method_id="live-contract",
                status=RunStatus.FAILED,
                stop_reason=StopReason.QUALITY_PASSED,
                best_version_id="v0",
                last_version_id="v0",
                versions=[version],
            )


if __name__ == "__main__":
    unittest.main()
