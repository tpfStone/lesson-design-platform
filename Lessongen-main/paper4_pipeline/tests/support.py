"""Hand-built domain fixtures; unit tests never pretend to be model calls."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
# Test fixtures are part of this standalone project after migration.
REPO_ROOT = PACKAGE_ROOT
SRC_ROOT = PACKAGE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


from paper4_pipeline.control.rules import check_lesson_plan  # noqa: E402
from paper4_pipeline.control.versioning import document_hash  # noqa: E402
from paper4_pipeline.domain.models import (  # noqa: E402
    CritiqueItem,
    CritiqueSource,
    EvaluationReport,
    ExperimentConfig,
    LearningObjective,
    LessonPlanDocument,
    LessonPlanVersion,
    LessonTask,
    LessonMetadata,
    LessonQuestion,
    ModelConfig,
    ProcedureStep,
    RubricDimension,
    RubricScores,
    Severity,
    TeachingResource,
)


FIXED_TIME = datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc)


def make_task() -> LessonTask:
    return LessonTask(
        task_id="unit-math-fractions",
        subject="数学",
        grade="五年级",
        topic="分数的意义",
        duration_minutes=45,
        course_information="五年级数学第一课时，45分钟",
        textbook_content="通过平均分情境理解单位一与分数意义。",
        curriculum_standards=["理解分数的意义，并能结合情境解释。"],
        learning_objectives=["结合情境解释分数的意义"],
        student_profile="学生已经理解平均分。",
        available_resources=["分数条"],
        required_sections=[
            "content_analysis",
            "student_analysis",
            "learning_objectives",
            "procedure_steps",
            "assessment_plan",
        ],
        source_refs=["fixture:fractions"],
    )


def make_document(
    task: LessonTask | None = None,
    *,
    high_quality: bool = False,
) -> LessonPlanDocument:
    task = task or make_task()
    objectives = [
        LearningObjective(
            objective_id="obj-1",
            description="结合平均分情境解释分数的意义",
            evidence_of_achievement=(
                "学生能结合一个平均分情境正确解释分数。"
                if high_quality
                else ""
            ),
            standard_refs=[task.curriculum_standards[0]],
        )
    ]
    resources = [
        TeachingResource(
            resource_id="res-1",
            name="分数条",
            description="用于表示整体与部分关系",
        )
    ]
    document = LessonPlanDocument(
        plan_id="unit-math-fractions-plan",
        task_id=task.task_id,
        metadata=LessonMetadata(
            subject=task.subject,
            grade=task.grade,
            topic=task.topic,
            duration_minutes=task.duration_minutes,
        ),
        curriculum_standards=list(task.curriculum_standards),
        content_analysis=task.textbook_content,
        student_analysis=task.student_profile,
        learning_objectives=objectives,
        key_points=["理解单位一与部分数量的关系"],
        difficult_points=["用语言解释分数含义"],
        teaching_strategy="情境问题与操作表征相结合。",
        resources=resources,
        procedure_steps=[
            ProcedureStep(
                step_id="step-1",
                stage="情境诊断",
                duration_minutes=10,
                objective_ids=["obj-1"],
                teacher_actions=["呈现平均分情境并追问整体。"],
                student_actions=["独立判断并说明整体与部分。"],
                questions=[
                    LessonQuestion(
                        question="这里把什么看作一个整体？",
                        expected_responses=["把完整的一份物品看作单位一。"],
                        possible_misconceptions=(
                            ["把部分数量误认为整体数量。"] if high_quality else []
                        ),
                    )
                ],
                assessment="观察学生能否正确指出单位一。",
                design_rationale="诊断学生对平均分的已有理解。",
                resource_ids=["res-1"],
            ),
            ProcedureStep(
                step_id="step-2",
                stage="操作建构",
                duration_minutes=20,
                objective_ids=["obj-1"],
                teacher_actions=["组织学生用分数条表示不同分数。"],
                student_actions=["操作、比较并解释每个分数。"],
                questions=[],
                assessment=(
                    "使用检查表记录学生的解释及其证据。" if high_quality else ""
                ),
                design_rationale="连接操作表征与符号含义。",
                resource_ids=["res-1"],
            ),
            ProcedureStep(
                step_id="step-3",
                stage="应用总结",
                duration_minutes=15,
                objective_ids=["obj-1"],
                teacher_actions=["提供变式并组织出口任务。"],
                student_actions=["解释新情境并完成出口任务。"],
                questions=[],
                assessment="依据出口任务判断目标达成。",
                design_rationale="检验学生能否迁移解释。",
                resource_ids=["res-1"],
            ),
        ],
        assessment_plan="结合课堂观察与出口任务收集目标证据。",
        differentiation=(
            "提供分数条支架，并为进阶学生增加反例辨析。"
            if high_quality
            else ""
        ),
        homework="画图解释两个不同分数。",
        board_design="单位一 → 平均分 → 分数表示",
        reflection="课后依据学生证据调整。",
        references=list(task.source_refs),
    )
    if high_quality:
        for step in document.procedure_steps:
            if not step.assessment:
                step.assessment = "使用检查表记录学生的解释及其证据。"
            for question in step.questions:
                question.possible_misconceptions = ["把部分数量误认为整体数量。"]
        document.differentiation = "提供分数条支架，并为进阶学生增加反例辨析。"
    return document


def make_config(**updates: object) -> ExperimentConfig:
    payload: dict[str, object] = {
        "experiment_id": "unit-exp",
        "method_id": "live-contract-unit-test",
        "role_model_configs": {
            profile_id: ModelConfig()
            for profile_id in (
                "design_architect_v0_1",
                "writer_v0_1",
                "subject_critic_v0_1",
                "pedagogy_critic_v0_1",
                "alignment_critic_v0_1",
                "validator_v0_1",
                "judge_v0_1",
                "rewriter_v0_1",
            )
        },
        "max_rounds": 3,
        "max_model_calls": 30,
        "max_total_tokens": 80_000,
        "max_estimated_cost": 10.0,
        "max_runtime_seconds": 600.0,
    }
    payload.update(updates)
    return ExperimentConfig.model_validate(payload)


def make_evaluation(
    version_id: str,
    *,
    score: float,
    high_risk_issue_ids: list[str] | None = None,
    unresolved_issue_count: int = 0,
    regressions: list[str] | None = None,
) -> EvaluationReport:
    scores = RubricScores(
        curriculum_alignment=score,
        knowledge_accuracy=score,
        teaching_logic=score,
        classroom_feasibility=score,
        differentiated_instruction=score,
        student_engagement=score,
        assessment_design=score,
        language_and_format=score,
    )
    return EvaluationReport(
        evaluation_id=f"eval-{version_id}",
        evaluated_version_id=version_id,
        rubric_scores=scores,
        overall_score=score,
        high_risk_issue_ids=high_risk_issue_ids or [],
        unresolved_issue_count=unresolved_issue_count,
        rule_checks_passed=True,
        regressions=regressions or [],
    )


def make_version(
    version_id: str,
    iteration: int,
    *,
    score: float,
    task: LessonTask | None = None,
    document: LessonPlanDocument | None = None,
    parent_version_id: str = "",
    high_risk_issue_ids: list[str] | None = None,
    regressions: list[str] | None = None,
    unresolved_issue_count: int = 0,
    change_count: int = 0,
) -> LessonPlanVersion:
    task = task or make_task()
    document = document or make_document(task, high_quality=True)
    rule_report = check_lesson_plan(document, task, report_id=f"rule-{version_id}")
    return LessonPlanVersion(
        version_id=version_id,
        parent_version_id=parent_version_id,
        iteration=iteration,
        document=document,
        created_by_profile_id="writer_v0_1" if iteration == 0 else "rewriter_v0_1",
        created_at=FIXED_TIME,
        document_hash=document_hash(document),
        rule_check_report=rule_report,
        internal_evaluation=make_evaluation(
            version_id,
            score=score,
            high_risk_issue_ids=high_risk_issue_ids,
            regressions=regressions,
            unresolved_issue_count=unresolved_issue_count,
        ),
        change_count=change_count,
    )


def make_critique(critique_id: str) -> CritiqueItem:
    return CritiqueItem(
        critique_id=critique_id,
        source=CritiqueSource.CRITIC,
        critic_profile_id="pedagogy_critic_v0_1",
        dimension=RubricDimension.DIFFERENTIATED_INSTRUCTION,
        issue_code="missing_differentiation",
        target_path="/differentiation",
        lesson_location="差异化支持",
        issue="缺少面向不同学习起点的支持。",
        evidence="differentiation 字段为空。",
        severity=Severity.MEDIUM,
        actionable_suggestion="增加基础支架和拓展任务。",
        introduced_in_round=1,
    )
