"""Read-only migration adapter for the existing tutorial34 dev fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from paper4_pipeline.domain.models import Language, LessonTask, TaskMode


_SECTION_MAP = {
    "学情分析": ["student_analysis"],
    "教学目标": ["learning_objectives"],
    "教学重难点": ["key_points", "difficult_points"],
    "教学过程": ["procedure_steps"],
    "评价与作业": ["assessment_plan", "homework"],
    "Learner Analysis": ["student_analysis"],
    "Learning Objectives": ["learning_objectives"],
    "Key and Difficult Points": ["key_points", "difficult_points"],
    "Lesson Procedure": ["procedure_steps"],
    "Assessment and Homework": ["assessment_plan", "homework"],
}


def tutorial_case_to_task(case: dict) -> LessonTask:
    """Normalize one legacy fixture without importing legacy runtime objects."""

    sections: list[str] = []
    for legacy_name in case.get("required_sections", []):
        sections.extend(_SECTION_MAP.get(legacy_name, []))
    metadata = dict(case.get("metadata", {}))
    metadata.update(
        {
            "migration_adapter": "tutorial34-v0.1-to-paper4-task-v0.1",
            "legacy_question": case.get("question", ""),
            "legacy_pair_id": case.get("pair_id", ""),
            "legacy_split": case.get("split", "dev"),
        }
    )
    return LessonTask(
        task_id=case["id"],
        mode=TaskMode.GENERATE,
        language=Language(case["language"]),
        subject=case["subject"],
        grade=case["grade"],
        topic=case["topic"],
        duration_minutes=case.get("duration_minutes", 45),
        course_information=case["course_information"],
        textbook_content=case.get("textbook_content", ""),
        learning_objectives=case.get("learning_objectives", []),
        class_constraints=case.get("constraints", {}),
        required_sections=list(dict.fromkeys(sections)),
        source_refs=case.get("source_refs", []),
        metadata=metadata,
    )


def load_tutorial34_tasks(path: Path) -> list[LessonTask]:
    tasks: list[LessonTask] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                tasks.append(tutorial_case_to_task(json.loads(line)))
            except Exception as exc:
                raise ValueError(f"invalid tutorial34 case at line {line_number}") from exc
    return tasks
