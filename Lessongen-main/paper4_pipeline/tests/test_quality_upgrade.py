from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from pydantic import ValidationError

from support import make_document, make_task

from paper4_pipeline.domain.models import (
    DesignCandidate,
    LessonDesignBlueprint,
    TeachingArtifact,
)

try:
    from docx import Document
    from paper4_pipeline.exporters.docx_exporter import export_docx

    HAVE_DOCX = True
except ImportError:  # python-docx is an optional exporter dependency
    HAVE_DOCX = False


class DesignFirstContractTests(unittest.TestCase):
    def test_blueprint_requires_real_selection(self) -> None:
        candidates = [
            DesignCandidate(
                candidate_id=f"c-{index}",
                title=f"路线{index}",
                design_thesis="用可比较证据推动概念形成",
                driving_question="不同表示为什么仍表达同一关系？",
                learner_starting_point="学生会操作但解释不稳定",
                desired_conceptual_shift="从操作结果转向关系解释",
                learning_arc=["诊断", "比较", "解释"],
                pivotal_moment="学生用反例修正原解释",
                student_products=["证据卡"],
                concrete_materials=["三组可比较案例"],
                subject_specific_value="突出整体与部分关系",
            )
            for index in (1, 2)
        ]
        blueprint = LessonDesignBlueprint(
            blueprint_id="blueprint-1",
            task_id="task-1",
            candidates=candidates,
            selected_candidate_id="c-2",
            selection_reason="证据链更清晰",
            quality_non_negotiables=["必须产出可检查的证据卡"],
        )

        self.assertEqual("c-2", blueprint.selected_candidate_id)

    def test_rich_content_fields_are_backward_compatible(self) -> None:
        document = make_document(make_task(), high_quality=True)
        document.design_thesis = "让学生用证据解释分数关系"
        document.driving_question = "同一个分数为什么可以有不同表示？"
        document.learning_trajectory = ["操作", "比较", "解释"]
        document.teaching_artifacts = [
            TeachingArtifact(
                artifact_id="artifact-1",
                artifact_type="出口任务",
                title="一分钟解释卡",
                content="任选一个分数，用图和一句话解释其含义。",
                answer_or_success_criteria="图、整体、平均分和份数相互一致。",
            )
        ]

        legacy_payload = document.model_dump(mode="json")
        for step in legacy_payload["procedure_steps"]:
            step.pop("artifact_ids")
        restored = type(document).model_validate(legacy_payload)

        self.assertEqual("一分钟解释卡", restored.teaching_artifacts[0].title)
        self.assertTrue(all(not step.artifact_ids for step in restored.procedure_steps))

    def test_steps_reference_resources_and_artifacts_in_separate_namespaces(self) -> None:
        document = make_document(make_task(), high_quality=True)
        document.teaching_artifacts = [
            TeachingArtifact(
                artifact_id="art-1",
                artifact_type="任务卡",
                title="分数证据卡",
                content="用图和一句话解释 3/4。",
            )
        ]
        document.procedure_steps[0].artifact_ids = ["art-1"]

        restored = type(document).model_validate(document.model_dump(mode="json"))

        self.assertEqual(["res-1"], restored.procedure_steps[0].resource_ids)
        self.assertEqual(["art-1"], restored.procedure_steps[0].artifact_ids)

    def test_artifact_id_cannot_be_misfiled_as_a_resource_id(self) -> None:
        document = make_document(make_task(), high_quality=True)
        document.teaching_artifacts = [
            TeachingArtifact(
                artifact_id="art-1",
                artifact_type="任务卡",
                title="分数证据卡",
                content="用图和一句话解释 3/4。",
            )
        ]
        payload = document.model_dump(mode="json")
        payload["procedure_steps"][0]["resource_ids"] = ["art-1"]

        with self.assertRaisesRegex(ValidationError, "unknown resources"):
            type(document).model_validate(payload)

    def test_unknown_artifact_reference_is_rejected(self) -> None:
        document = make_document(make_task(), high_quality=True)
        payload = document.model_dump(mode="json")
        payload["procedure_steps"][0]["artifact_ids"] = ["art-missing"]

        with self.assertRaisesRegex(ValidationError, "unknown teaching artifacts"):
            type(document).model_validate(payload)


@unittest.skipUnless(HAVE_DOCX, "python-docx is not installed; skipping docx layout checks")
class NeutralDocxLayoutTests(unittest.TestCase):
    def test_export_is_a4_neutral_and_uses_three_column_process(self) -> None:
        document = make_document(make_task(), high_quality=True)
        document.design_thesis = "让学生用证据解释分数关系"
        document.driving_question = "什么决定了一个分数的含义？"
        document.learning_trajectory = ["暴露直觉", "比较表征", "解释迁移"]
        document.teaching_artifacts = [
            TeachingArtifact(
                artifact_id="artifact-1",
                artifact_type="任务卡",
                title="分数证据卡",
                purpose="收集解释证据",
                content="画出 3/4，并标明整体、平均分份数和所取份数。",
                answer_or_success_criteria="四项信息一致且解释完整。",
            )
        ]
        for step in document.procedure_steps:
            step.artifact_ids = ["artifact-1"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lesson.docx"
            export_docx(
                document,
                path,
                run_id="test-run",
                best_version_id="v1",
                last_version_id="v1",
            )
            exported = Document(path)
            section = exported.sections[0]
            self.assertAlmostEqual(8.27, section.page_width.inches, places=2)
            self.assertAlmostEqual(11.69, section.page_height.inches, places=2)
            self.assertTrue(any(len(table.columns) == 3 for table in exported.tables))
            with zipfile.ZipFile(path) as archive:
                xml = archive.read("word/document.xml").decode("utf-8")
            self.assertIn("使用材料", xml)
            self.assertIn("分数证据卡", xml)
            self.assertNotIn("2E74B5", xml)
            self.assertNotIn("1F4E79", xml)


if __name__ == "__main__":
    unittest.main()
