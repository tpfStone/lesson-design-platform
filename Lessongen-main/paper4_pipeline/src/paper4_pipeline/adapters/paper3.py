"""Translate Paper#3 classroom-simulation evidence into Paper#4 critiques."""

from __future__ import annotations

from paper4_pipeline.domain.ids import stable_id
from paper4_pipeline.domain.models import (
    CritiqueBatch,
    CritiqueItem,
    CritiqueSource,
    RubricDimension,
    SimulationReport,
)


_DIMENSION_BY_TYPE = {
    "misconception": RubricDimension.KNOWLEDGE_ACCURACY,
    "timing": RubricDimension.CLASSROOM_FEASIBILITY,
    "engagement": RubricDimension.STUDENT_ENGAGEMENT,
    "feasibility": RubricDimension.CLASSROOM_FEASIBILITY,
    "differentiation": RubricDimension.DIFFERENTIATED_INSTRUCTION,
}


def simulation_report_to_critiques(
    report: SimulationReport,
    round_index: int,
) -> CritiqueBatch:
    items: list[CritiqueItem] = []
    for issue in report.issues:
        if issue.procedure_step_id:
            target_path = f"/procedure_steps/{issue.procedure_step_id}"
            location = f"教学过程/{issue.procedure_step_id}"
        elif issue.type == "differentiation":
            target_path = "/differentiation"
            location = "差异化支持"
        else:
            target_path = "/procedure_steps"
            location = issue.lesson_section_id or "教学过程"
        items.append(
            CritiqueItem(
                critique_id=stable_id(
                    "simulation-critique", report.simulation_id, issue.issue_id
                ),
                source=CritiqueSource.SIMULATION,
                dimension=_DIMENSION_BY_TYPE[issue.type],
                issue_code=f"simulation_{issue.type}",
                target_path=target_path,
                lesson_location=location,
                lesson_section_id=issue.lesson_section_id,
                procedure_step_id=issue.procedure_step_id,
                issue=issue.description,
                evidence=(
                    "课堂模拟事件：" + "、".join(issue.evidence_event_ids)
                    if issue.evidence_event_ids
                    else "课堂模拟报告中的结构化观察"
                ),
                severity=issue.severity,
                actionable_suggestion=issue.suggestion,
                confidence=issue.confidence,
                introduced_in_round=round_index,
                knowledge_source_refs=[f"simulation:{report.simulation_id}"],
            )
        )
    return CritiqueBatch(
        batch_id=stable_id("simulation-batch", report.simulation_id, round_index),
        plan_version_id=report.lesson_plan_version_id,
        round_index=round_index,
        items=items,
    )
