"""Deterministic structural evidence for the Alignment Critic."""

from __future__ import annotations

from paper4_pipeline.domain.models import LessonPlanDocument, LessonTask


def build_alignment_audit(
    document: LessonPlanDocument,
    task: LessonTask,
) -> dict[str, object]:
    """Map objectives to activities and evidence without judging semantics."""

    linked: dict[str, list[object]] = {
        item.objective_id: [] for item in document.learning_objectives
    }
    empty: dict[str, list[str]] = {
        "steps_without_objectives": [],
        "steps_without_assessment": [],
        "steps_without_student_product": [],
        "steps_without_success_criteria": [],
    }
    for step in document.procedure_steps:
        if not step.objective_ids:
            empty["steps_without_objectives"].append(step.step_id)
        if not step.assessment.strip():
            empty["steps_without_assessment"].append(step.step_id)
        if not step.student_product.strip() and not step.artifact_ids:
            empty["steps_without_student_product"].append(step.step_id)
        if not step.success_criteria:
            empty["steps_without_success_criteria"].append(step.step_id)
        for objective_id in step.objective_ids:
            linked.setdefault(objective_id, []).append(
                {
                    "step_id": step.step_id,
                    "stage": step.stage,
                    "assessment": step.assessment,
                    "student_product": step.student_product,
                    "success_criteria": list(step.success_criteria),
                    "artifact_ids": list(step.artifact_ids),
                }
            )

    rows: list[dict[str, object]] = []
    empty["objectives_without_standard_refs"] = []
    empty["objectives_without_evidence"] = []
    empty["objectives_without_steps"] = []
    for objective in document.learning_objectives:
        # Missing objective references are actionable only when the task
        # actually supplied authoritative standards.  Otherwise this is an
        # upstream input limitation, not a defect Rewriter can repair.
        if task.curriculum_standards and not objective.standard_refs:
            empty["objectives_without_standard_refs"].append(objective.objective_id)
        if not objective.evidence_of_achievement.strip():
            empty["objectives_without_evidence"].append(objective.objective_id)
        if not linked.get(objective.objective_id):
            empty["objectives_without_steps"].append(objective.objective_id)
        rows.append(
            {
                "objective_id": objective.objective_id,
                "description": objective.description,
                "standard_refs": list(objective.standard_refs),
                "evidence_of_achievement": objective.evidence_of_achievement,
                "linked_steps": linked.get(objective.objective_id, []),
            }
        )

    messages = {
        "steps_without_objectives": "教学步骤没有关联学习目标。",
        "steps_without_assessment": "教学步骤没有声明评价或证据收集方式。",
        "steps_without_student_product": "教学步骤没有声明学生产出或教学产物。",
        "steps_without_success_criteria": "教学步骤没有声明成功标准。",
        "objectives_without_standard_refs": "学习目标没有声明课程标准或任务依据。",
        "objectives_without_evidence": "学习目标没有声明可观察的达成证据。",
        "objectives_without_steps": "学习目标没有被任何教学步骤承接。",
    }
    warnings = [
        {"code": code, "affected_ids": ids, "message": messages[code]}
        for code, ids in empty.items()
        if ids
    ]
    if task.curriculum_standards and not document.curriculum_standards:
        warnings.append(
            {
                "code": "task_standards_missing_from_plan",
                "affected_ids": [],
                "message": "任务提供了课程标准，但教案课程标准字段为空。",
            }
        )
    if not document.assessment_plan.strip():
        warnings.append(
            {
                "code": "assessment_plan_missing",
                "affected_ids": [],
                "message": "教案没有整体评价方案。",
            }
        )
    input_limitations = []
    if not task.curriculum_standards:
        input_limitations.append(
            {
                "code": "task_curriculum_standards_unavailable",
                "message": (
                    "任务未提供权威课程标准；只能审查目标、活动、产出与评价的"
                    "内部一致性，不能要求 Rewriter 补造课标条款或 standard_refs。"
                ),
            }
        )
    return {
        "audit_version": "objective-activity-evidence-v0.2",
        "purpose": "只提供结构映射与缺失信号，不代替语义、学科或教学判断。",
        "task_curriculum_standards": list(task.curriculum_standards),
        "plan_curriculum_standards": list(document.curriculum_standards),
        "objective_traceability": rows,
        "global_assessment_plan": document.assessment_plan,
        "warnings": warnings,
        "input_limitations": input_limitations,
    }
