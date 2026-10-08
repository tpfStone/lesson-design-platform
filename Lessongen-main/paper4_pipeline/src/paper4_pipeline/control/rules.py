"""Deterministic hard checks and diagnostic warnings for lesson plans."""

from __future__ import annotations

from paper4_pipeline.domain.models import (
    LessonPlanDocument,
    LessonTask,
    RuleCheckReport,
    RuleViolation,
    Severity,
)


_MISSING_PATH_VALUE = object()


def _decode_pointer_segment(raw: str) -> str:
    """Decode the two escape sequences defined by JSON Pointer (RFC 6901)."""

    return raw.replace("~1", "/").replace("~0", "~")


def _document_path_value(document: LessonPlanDocument, target_path: str) -> object:
    """Resolve a critic target path by list index or a domain ``*_id`` value."""

    if not target_path.startswith("/"):
        return _MISSING_PATH_VALUE
    current: object = document.model_dump(mode="python")
    for raw_segment in target_path.split("/")[1:]:
        segment = _decode_pointer_segment(raw_segment)
        if isinstance(current, dict):
            if segment not in current:
                return _MISSING_PATH_VALUE
            current = current[segment]
            continue
        if isinstance(current, list):
            if segment.isdigit():
                index = int(segment)
                if index >= len(current):
                    return _MISSING_PATH_VALUE
                current = current[index]
                continue
            match = next(
                (
                    item
                    for item in current
                    if isinstance(item, dict)
                    and any(
                        key.endswith("_id") and value == segment
                        for key, value in item.items()
                    )
                ),
                _MISSING_PATH_VALUE,
            )
            if match is _MISSING_PATH_VALUE:
                return _MISSING_PATH_VALUE
            current = match
            continue
        return _MISSING_PATH_VALUE
    return current


def lesson_target_changed(
    before: LessonPlanDocument,
    after: LessonPlanDocument,
    target_path: str,
) -> bool:
    """Return whether a claimed rewrite target has an observable data change.

    A path that resolves in neither document is not evidence of a change. A
    create/delete operation is a change when the path resolves on only one side.
    """

    before_value = _document_path_value(before, target_path)
    after_value = _document_path_value(after, target_path)
    if before_value is _MISSING_PATH_VALUE and after_value is _MISSING_PATH_VALUE:
        return False
    if (before_value is _MISSING_PATH_VALUE) != (after_value is _MISSING_PATH_VALUE):
        return True
    return before_value != after_value


def check_lesson_plan(
    document: LessonPlanDocument,
    task: LessonTask,
    duration_tolerance_minutes: int = 2,
    report_id: str | None = None,
) -> RuleCheckReport:
    """Check constraints that must not be delegated to a language model.

    Structural referential integrity is already enforced by Pydantic.  This
    function adds task-specific constraints and keeps softer quality signals as
    warnings so they can drive critics without making valid drafts unloadable.
    """

    violations: list[RuleViolation] = []
    total_duration = sum(step.duration_minutes for step in document.procedure_steps)

    def add(code: str, message: str, location: str, severity: Severity) -> None:
        violations.append(
            RuleViolation(
                code=code,
                message=message,
                location=location,
                severity=severity,
            )
        )

    if not document.learning_objectives:
        add(
            "missing_learning_objectives",
            "教案至少需要一个学习目标。",
            "learning_objectives",
            Severity.CRITICAL,
        )
    if document.task_id != task.task_id:
        add(
            "task_id_mismatch",
            "教案 task_id 与运行任务不一致。",
            "task_id",
            Severity.CRITICAL,
        )
    for field_name in ("subject", "grade", "topic", "duration_minutes"):
        if getattr(document.metadata, field_name) != getattr(task, field_name):
            add(
                f"metadata_{field_name}_mismatch",
                f"教案 metadata.{field_name} 与任务不一致。",
                f"metadata.{field_name}",
                Severity.HIGH,
            )
    if not document.procedure_steps:
        add(
            "missing_procedure_steps",
            "教案至少需要一个教学步骤。",
            "procedure_steps",
            Severity.CRITICAL,
        )
    if abs(total_duration - task.duration_minutes) > duration_tolerance_minutes:
        add(
            "duration_mismatch",
            f"教学步骤合计 {total_duration} 分钟，与任务要求的 "
            f"{task.duration_minutes} 分钟不一致。",
            "procedure_steps",
            Severity.HIGH,
        )
    if task.curriculum_standards and not document.curriculum_standards:
        add(
            "missing_curriculum_alignment",
            "任务给出了课程标准，但教案没有记录标准依据。",
            "curriculum_standards",
            Severity.HIGH,
        )

    for required_section in task.required_sections:
        if not hasattr(document, required_section):
            add(
                "unknown_required_section",
                f"任务要求了未知章节：{required_section}。",
                f"required_sections.{required_section}",
                Severity.HIGH,
            )
            continue
        value = getattr(document, required_section)
        if value is None or value == "" or value == []:
            add(
                "empty_required_section",
                f"任务要求的章节 {required_section} 为空。",
                required_section,
                Severity.HIGH,
            )

    for objective in document.learning_objectives:
        if not objective.evidence_of_achievement.strip():
            add(
                "objective_without_evidence",
                f"目标 {objective.objective_id} 缺少可观察的达成证据。",
                f"learning_objectives.{objective.objective_id}",
                Severity.MEDIUM,
            )
    for step in document.procedure_steps:
        if not step.objective_ids:
            add(
                "step_without_objective",
                f"步骤 {step.step_id} 未关联学习目标。",
                f"procedure_steps.{step.step_id}",
                Severity.MEDIUM,
            )
        if not step.assessment.strip():
            add(
                "step_without_assessment",
                f"步骤 {step.step_id} 缺少形成性评价。",
                f"procedure_steps.{step.step_id}",
                Severity.MEDIUM,
            )
        if not step.student_product.strip():
            add(
                "step_without_student_product",
                f"步骤 {step.step_id} 未说明可观察的学生产出。",
                f"procedure_steps.{step.step_id}.student_product",
                Severity.MEDIUM,
            )
        if not step.success_criteria:
            add(
                "step_without_success_criteria",
                f"步骤 {step.step_id} 缺少学生产出的成功标准。",
                f"procedure_steps.{step.step_id}.success_criteria",
                Severity.MEDIUM,
            )
    for field_name, code, message in (
        ("design_thesis", "missing_design_thesis", "教案缺少可贯穿全课的设计主张。"),
        ("driving_question", "missing_driving_question", "教案缺少驱动学习的核心问题。"),
        ("learning_trajectory", "missing_learning_trajectory", "教案缺少清晰的学习轨迹。"),
    ):
        value = getattr(document, field_name)
        if not value:
            add(code, message, field_name, Severity.MEDIUM)
    if not document.teaching_artifacts:
        add(
            "missing_ready_to_use_artifact",
            "教案没有提供可直接使用的例题、语料、任务单或评价材料。",
            "teaching_artifacts",
            Severity.MEDIUM,
        )
    if not document.differentiation.strip():
        add(
            "missing_differentiation",
            "教案缺少差异化支持策略。",
            "differentiation",
            Severity.MEDIUM,
        )

    checks = {
        "has_learning_objectives": bool(document.learning_objectives),
        "has_procedure_steps": bool(document.procedure_steps),
        "duration_within_tolerance": abs(total_duration - task.duration_minutes)
        <= duration_tolerance_minutes,
        "curriculum_alignment_present": not task.curriculum_standards
        or bool(document.curriculum_standards),
        "task_document_consistent": document.task_id == task.task_id
        and document.metadata.subject == task.subject
        and document.metadata.grade == task.grade
        and document.metadata.topic == task.topic
        and document.metadata.duration_minutes == task.duration_minutes,
        "required_sections_present": not any(
            item.code in {"unknown_required_section", "empty_required_section"}
            for item in violations
        ),
        "references_resolved": True,  # enforced by LessonPlanDocument validation
    }
    hard_severities = {Severity.HIGH, Severity.CRITICAL}
    passed = not any(item.severity in hard_severities for item in violations)
    return RuleCheckReport(
        report_id=report_id or f"rule-{document.plan_id}",
        plan_id=document.plan_id,
        passed=passed,
        checks=checks,
        violations=violations,
        total_duration_minutes=total_duration,
        expected_duration_minutes=task.duration_minutes,
    )


def hard_rule_regressions(
    before: LessonPlanDocument,
    after: LessonPlanDocument,
    task: LessonTask,
    duration_tolerance_minutes: int = 2,
) -> list[str]:
    """Describe deterministic hard-rule regressions introduced by an edit.

    Imported lessons are allowed to enter optimization with pre-existing hard
    violations.  A local patch therefore must not be required to repair every
    unrelated baseline defect in one call.  It is acceptable when it removes
    or preserves the baseline's blocking violations, but never when it creates
    a new one or makes an already-invalid duration further from the task.
    """

    before_report = check_lesson_plan(before, task, duration_tolerance_minutes)
    after_report = check_lesson_plan(after, task, duration_tolerance_minutes)
    hard = {Severity.HIGH, Severity.CRITICAL}

    def keys(report: RuleCheckReport) -> set[tuple[str, str]]:
        return {
            (item.code, item.location)
            for item in report.violations
            if item.severity in hard
        }

    regressions = [
        f"new hard violation: {code} at {location}"
        for code, location in sorted(keys(after_report) - keys(before_report))
    ]
    for check_name, was_ok in before_report.checks.items():
        if was_ok and not after_report.checks.get(check_name, False):
            regressions.append(f"hard check regressed: {check_name}")

    before_delta = abs(
        before_report.total_duration_minutes - before_report.expected_duration_minutes
    )
    after_delta = abs(
        after_report.total_duration_minutes - after_report.expected_duration_minutes
    )
    if before_delta > duration_tolerance_minutes and after_delta > before_delta:
        regressions.append(
            f"duration mismatch worsened: {before_delta} -> {after_delta} minutes"
        )
    return regressions
