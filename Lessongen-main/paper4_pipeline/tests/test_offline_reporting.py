from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paper4_pipeline.observability.report import (
    analyze_artifacts,
    export_process_report,
)


def _run_result(run_id: str, score: float, alignment: float) -> dict[str, object]:
    scores = {
        "curriculum_alignment": alignment,
        "knowledge_accuracy": score,
        "teaching_logic": score,
        "classroom_feasibility": score,
        "differentiated_instruction": score,
        "student_engagement": score,
        "assessment_design": score,
        "language_and_format": score,
    }
    return {
        "run_id": run_id,
        "status": "completed",
        "stop_reason": "quality_passed",
        "best_version_id": "v0",
        "last_version_id": "v0",
        "model_call_count": 3,
        "estimated_cost": 0.1,
        "versions": [
            {
                "version_id": "v0",
                "iteration": 0,
                "internal_evaluation": {
                    "overall_score": score,
                    "rubric_scores": scores,
                },
            }
        ],
        "critiques": [],
        "validation_batches": [],
        "rewrite_records": [],
        "route_decisions": [],
    }


class OfflineReportingTests(unittest.TestCase):
    def test_analyze_saved_runs_without_model_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, score in (("run-a", 7.5), ("run-b", 8.5)):
                run_dir = root / name
                run_dir.mkdir()
                (run_dir / "run_result.json").write_text(
                    json.dumps(_run_result(name, score, 6.5), ensure_ascii=False),
                    encoding="utf-8",
                )

            report = analyze_artifacts(root)

        self.assertEqual(0, report["model_calls_made"])
        self.assertEqual(2, report["run_count"])
        self.assertEqual(8.0, report["best_score_distribution"]["mean"])
        self.assertEqual("run-b", report["runs"][0]["run_id"])

    def test_export_process_report_uses_only_saved_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "run_result.json").write_text(
                json.dumps(_run_result("run-a", 8.0, 7.0), ensure_ascii=False),
                encoding="utf-8",
            )
            event = {
                "sequence": 1,
                "event_type": "run_started",
                "stage": "run",
                "actor_profile_id": "program",
                "round_index": 0,
                "version_id": "",
                "status": "ok",
                "duration_seconds": 0,
                "estimated_cost": 0,
                "input_summary": {"task": "saved"},
                "output_summary": None,
            }
            (run_dir / "trace.jsonl").write_text(
                json.dumps(event, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            output = export_process_report(run_dir, include_payloads=False)
            content = output.read_text(encoding="utf-8")

        self.assertIn("完全由已保存", content)
        self.assertIn("run_started", content)
        self.assertNotIn('"task": "saved"', content)


if __name__ == "__main__":
    unittest.main()
