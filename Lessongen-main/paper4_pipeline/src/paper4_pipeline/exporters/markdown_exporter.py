"""Readable Markdown rendering of the canonical lesson-plan document."""

from __future__ import annotations

from pathlib import Path

from paper4_pipeline.domain.models import LessonPlanDocument, PipelineResult, TaskMode
from paper4_pipeline.control.optimization import optimization_summary
from paper4_pipeline.exporters.common import atomic_write_text
from paper4_pipeline.exporters.json_exporter import best_version


def _cell(value: str | list[str]) -> str:
    text = "；".join(value) if isinstance(value, list) else value
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")


def render_markdown(
    document: LessonPlanDocument,
    *,
    run_id: str,
    best_version_id: str,
    last_version_id: str,
    status_notice: str = "",
) -> str:
    lines = [
        f"# {document.metadata.topic}教学设计",
        "",
    ]
    if status_notice:
        lines.extend([f"> **注意：{status_notice}**", ""])
    lines.extend(
        [
        f"> 运行 `{run_id}` · 最佳版本 `{best_version_id}` · "
        f"最后版本 `{last_version_id}` · 结构 `{document.schema_version}`",
        "",
        "| 学科 | 年级 | 课题 | 课时 |",
        "|---|---|---|---:|",
        f"| {_cell(document.metadata.subject)} | {_cell(document.metadata.grade)} | "
        f"{_cell(document.metadata.topic)} | {document.metadata.duration_minutes} 分钟 |",
        "",
        ]
    )

    def text_section(title: str, value: str) -> None:
        if value.strip():
            lines.extend([f"## {title}", "", value.strip(), ""])

    def list_section(title: str, values: list[str]) -> None:
        if values:
            lines.extend([f"## {title}", ""])
            lines.extend(f"- {item}" for item in values)
            lines.append("")

    list_section("课程标准依据", document.curriculum_standards)
    text_section("教学内容分析", document.content_analysis)
    text_section("学情分析", document.student_analysis)
    text_section("教学设计主张", document.design_thesis)
    text_section("驱动问题", document.driving_question)
    list_section("学习轨迹", document.learning_trajectory)
    if document.learning_objectives:
        lines.extend(
            [
                "## 学习目标与达成证据",
                "",
                "| 编号 | 学习目标 | 达成证据 | 标准关联 |",
                "|---|---|---|---|",
            ]
        )
        for item in document.learning_objectives:
            lines.append(
                f"| {_cell(item.objective_id)} | {_cell(item.description)} | "
                f"{_cell(item.evidence_of_achievement)} | {_cell(item.standard_refs)} |"
            )
        lines.append("")
    list_section("教学重点", document.key_points)
    list_section("教学难点", document.difficult_points)
    text_section("教学策略", document.teaching_strategy)
    if document.resources:
        lines.extend(["## 教学资源", ""])
        lines.extend(
            f"- **{item.name}**：{item.description}"
            + (f"<br>可用内容：{_cell(item.ready_to_use_content)}" if item.ready_to_use_content else "")
            for item in document.resources
        )
        lines.append("")
    if document.procedure_steps:
        resource_names = {item.resource_id: item.name for item in document.resources}
        artifact_titles = {
            item.artifact_id: item.title for item in document.teaching_artifacts
        }
        lines.extend(
            [
                "## 教学过程",
                "",
                "| 环节与教师活动 | 学生任务与产出 | 评价与调控 |",
                "|---|---|---|",
            ]
        )
        for step in document.procedure_steps:
            questions: list[str] = []
            for question in step.questions:
                item = question.question
                if question.expected_responses:
                    item += "（预期：" + "；".join(question.expected_responses) + "）"
                if question.teacher_follow_ups:
                    item += "（追问：" + "；".join(question.teacher_follow_ups) + "）"
                if question.possible_misconceptions:
                    item += "（预判：" + "；".join(question.possible_misconceptions) + "）"
                questions.append(item)
            branches = [
                f"若{item.trigger}，则{item.teacher_move}" for item in step.response_branches
            ]
            teacher = [
                f"**{step.stage}（{step.duration_minutes}分钟）**",
                *step.teacher_actions,
                *questions,
            ]
            if step.transition:
                teacher.append("过渡：" + step.transition)
            if step.resource_ids:
                teacher.append(
                    "使用资源："
                    + "；".join(resource_names[item] for item in step.resource_ids)
                )
            if step.artifact_ids:
                teacher.append(
                    "使用材料："
                    + "；".join(artifact_titles[item] for item in step.artifact_ids)
                )
            student = [*step.student_actions]
            if step.student_product:
                student.append("产出：" + step.student_product)
            student.extend("标准：" + item for item in step.success_criteria)
            student.extend("支架：" + item for item in step.scaffolds)
            student.extend("拓展：" + item for item in step.extensions)
            control = [step.assessment, *branches]
            lines.append(
                f"| {_cell(teacher)} | {_cell(student)} | {_cell(control)} |"
            )
        lines.append("")
    if document.teaching_artifacts:
        lines.extend(["## 可直接使用的教学材料", ""])
        for index, artifact in enumerate(document.teaching_artifacts, start=1):
            lines.extend(
                [
                    f"### 材料 {index}：{artifact.title}",
                    "",
                    f"- 类型：{artifact.artifact_type}",
                    f"- 用途：{artifact.purpose}",
                    "",
                    artifact.content,
                    "",
                ]
            )
            if artifact.answer_or_success_criteria:
                lines.extend(
                    ["**答案/成功标准：**", "", artifact.answer_or_success_criteria, ""]
                )
    text_section("总体评价设计", document.assessment_plan)
    text_section("差异化支持", document.differentiation)
    text_section("作业设计", document.homework)
    text_section("板书设计", document.board_design)
    text_section("课后观察与反思", document.reflection)
    list_section("参考材料", document.references)
    return "\n".join(lines).rstrip() + "\n"


def export_best_markdown(result: PipelineResult, path: Path) -> Path:
    version = best_version(result)
    if result.status.value == "failed":
        reason = result.stop_reason.value if result.stop_reason else "unknown"
        notice = (
            f"本文件是失败运行的恢复草稿（{reason}），未经最终验收，"
            "不能视为正式最佳教案。"
        )
    elif result.status.value == "needs_human":
        notice = "版本选择存在歧义或风险，必须经教师/专家确认后使用。"
    else:
        notice = ""
    content = render_markdown(
            version.document,
            run_id=result.run_id,
            best_version_id=result.best_version_id,
            last_version_id=result.last_version_id,
            status_notice=notice,
        )
    if result.task_mode == TaskMode.OPTIMIZE:
        summary = optimization_summary(result)
        content += (
            "\n## 本次优化核验\n\n"
            f"- 结果：{summary['message']}\n"
            f"- 原稿版本：`{summary['baseline_version_id']}`；交付版本：`{summary['selected_version_id']}`\n"
            f"- 实际变化栏目：{summary['changed_section_count']}；审查意见：{summary['critique_count']}；"
            f"改写轮次：{summary['rewrite_count']}\n"
            f"- 内部修订门槛：{('通过' if summary['quality_gate']['passed'] else '未通过') if summary['quality_gate'] else '未记录'}；"
            f"双顺序对照：{summary['pairwise_comparison']['verdict'] if summary['pairwise_comparison'] else '未执行'}\n"
            f"- 评分说明：{summary['score_notice']}\n"
            "- 具体修改前后内容见 `optimization_report.md` / `optimization_report.json`。\n"
        )
    atomic_write_text(path, content)
    return path
