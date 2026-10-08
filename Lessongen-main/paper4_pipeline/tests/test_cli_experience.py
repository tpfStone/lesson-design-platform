from __future__ import annotations

import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from support import make_task

from paper4_pipeline.cli import (
    DEFAULT_CONFIG,
    DEFAULT_OUTPUT,
    build_parser,
    collect_interactive_task,
    main,
)
from paper4_pipeline.domain.naming import (
    automatic_run_id,
    automatic_task_id,
    safe_name_component,
)


class CommandDefaultsTests(unittest.TestCase):
    def test_shipped_config_is_calibrated_for_a_three_round_product_run(self) -> None:
        config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))

        self.assertEqual(3, config["max_rounds"])
        self.assertEqual(3, config["optimization_max_rounds"])
        self.assertEqual(8.0, config["quality_threshold"])
        self.assertEqual(8.0, config["optimization_quality_threshold"])
        self.assertEqual(0.2, config["optimization_min_score_gain"])
        self.assertEqual(7.0, config["critical_dimension_floor"])
        # Three patch-based optimization rounds can consume substantially more
        # calls/tokens; do not silently raise the generation budget as well.
        self.assertEqual(42, config["max_model_calls"])
        self.assertEqual(360000, config["max_total_tokens"])
        self.assertEqual(60, config["optimization_max_model_calls"])
        self.assertEqual(720000, config["optimization_max_total_tokens"])
        self.assertTrue(config["enable_docx"])

    def test_run_only_requires_task_path(self) -> None:
        args = build_parser().parse_args(["run", "--task", "lesson.json"])

        self.assertEqual(DEFAULT_CONFIG, args.config)
        self.assertEqual(DEFAULT_OUTPUT, args.output)
        self.assertIsNone(args.run_id)
        # --docx not given: leave it None so config.enable_docx governs.
        self.assertIsNone(args.docx)

    def test_generate_has_safe_zero_argument_defaults(self) -> None:
        args = build_parser().parse_args(["generate"])

        self.assertEqual(DEFAULT_CONFIG, args.config)
        self.assertEqual(DEFAULT_OUTPUT, args.output)
        self.assertIsNone(args.run_name)
        self.assertIsNone(args.docx)
        self.assertFalse(args.yes)

    def test_offline_commands_have_safe_defaults(self) -> None:
        analyze = build_parser().parse_args(["analyze"])
        process = build_parser().parse_args(
            ["export-process", "--run-dir", "artifacts/example"]
        )

        self.assertEqual(DEFAULT_OUTPUT, analyze.artifacts)
        self.assertEqual(Path("artifacts/example"), process.run_dir)
        self.assertIsNone(process.output)
        self.assertFalse(process.summary_only)

    def test_expected_cli_file_error_is_json_not_a_traceback(self) -> None:
        missing = Path("definitely-missing-run-result.json")
        output = StringIO()

        with redirect_stdout(output):
            exit_code = main(["inspect", "--result", str(missing)])

        self.assertEqual(2, exit_code)
        payload = json.loads(output.getvalue())
        self.assertEqual("error", payload["status"])
        self.assertEqual("FileNotFoundError", payload["error_type"])
        self.assertNotIn("Traceback", output.getvalue())


class InteractiveTaskTests(unittest.TestCase):
    def test_only_subject_grade_and_topic_are_required(self) -> None:
        responses = iter(
            [
                "数学",
                "八年级",
                "勾股定理",
                "",  # duration -> 45
                "",  # course information -> automatic
                "",  # textbook version
                "",  # textbook content
                "",  # standards
                "",  # objectives
                "",  # student profile
                "",  # class size
                "",  # resources
                "",  # additional requirements
                "",  # style -> model chooses
                "",  # detail -> showcase
                "",  # run name -> automatic
            ]
        )
        task, run_name = collect_interactive_task(
            input_fn=lambda _: next(responses),
            output_fn=lambda _: None,
        )

        self.assertEqual("数学", task.subject)
        self.assertEqual("八年级", task.grade)
        self.assertEqual("勾股定理", task.topic)
        self.assertEqual(45, task.duration_minutes)
        self.assertEqual("八年级数学《勾股定理》，45分钟", task.course_information)
        self.assertEqual([], task.learning_objectives)
        self.assertEqual("showcase", task.metadata["detail_level"])
        self.assertEqual("", run_name)


class FriendlyNamingTests(unittest.TestCase):
    def test_run_name_is_readable_unique_and_windows_safe(self) -> None:
        task = make_task()
        now = datetime(2026, 9, 3, 13, 5, 9, tzinfo=timezone.utc)

        run_id = automatic_run_id(
            task,
            label="公开课/第一版:*?",
            now=now,
            suffix="abc123",
        )
        task_id = automatic_task_id(
            task.subject,
            task.grade,
            task.topic,
            now=now,
            suffix="def456",
        )

        self.assertEqual("20260903-130509-公开课-第一版-abc123", run_id)
        self.assertTrue(task_id.startswith("lesson-20260903-130509-数学-五年级-分数的意义"))
        self.assertNotRegex(run_id, r'[<>:"/\\|?*]')
        self.assertEqual("lesson-CON", safe_name_component("CON"))


if __name__ == "__main__":
    unittest.main()
