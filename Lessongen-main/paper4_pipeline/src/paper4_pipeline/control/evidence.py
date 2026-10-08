"""Deterministic task-input evidence profiling.

The profile does not invent missing curriculum or textbook evidence and does
not change rubric weights.  It tells model-backed reviewers which claims can
be externally verified and which dimensions must be assessed from the lesson
plan's internal evidence only.
"""

from __future__ import annotations

from paper4_pipeline.domain.models import LessonTask


def build_task_evidence_profile(task: LessonTask) -> dict[str, object]:
    """Return a JSON-safe description of available and missing task evidence."""

    available = {
        "curriculum_standards": bool(task.curriculum_standards),
        "textbook_context": bool(task.textbook_content.strip()),
        "learner_context": bool(task.student_profile.strip()),
        "learning_objectives": bool(task.learning_objectives),
    }
    missing = [name for name, present in available.items() if not present]
    supplied_count = sum(available.values())
    if supplied_count == len(available):
        level = "full"
    elif supplied_count >= 2:
        level = "partial"
    else:
        level = "minimal"

    limitations: list[str] = []
    if not available["curriculum_standards"]:
        limitations.append(
            "未提供权威课程标准：可评价目标—活动—产出—评价的内部一致性，"
            "但不能核验外部课标条款，也不得因此补造课标编号。"
        )
    if not available["textbook_context"]:
        limitations.append(
            "未提供教材内容：可评价通用学科准确性，但不能确认教材版本边界与表述一致性。"
        )
    if not available["learner_context"]:
        limitations.append(
            "未提供具体学情：差异化与难度适配只能作为待教师复核的设计假设。"
        )
    if not available["learning_objectives"]:
        limitations.append(
            "未提供预设学习目标：目标由设计器与写作器提出，应评价其可观察性和内部闭环。"
        )

    return {
        "profile_version": "task-evidence-v0.1",
        "readiness_level": level,
        "available": available,
        "missing_fields": missing,
        "limitations": limitations,
        "scoring_policy": {
            "keep_all_eight_dimensions": True,
            "do_not_invent_missing_sources": True,
            "curriculum_alignment": (
                "有课标时评价外部课标对齐与内部一致性；无课标时只评价内部"
                "目标—活动—产出—评价一致性，并在 summary 披露外部对齐未核验。"
            ),
            "knowledge_accuracy": (
                "无教材原文时仍评价明显事实错误与概念边界，但披露教材版本边界未核验。"
            ),
        },
    }
