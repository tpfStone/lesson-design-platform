"""Auditable role-specific knowledge bundles for the first live experiment."""

from __future__ import annotations

import hashlib
from pathlib import Path

from paper4_pipeline.domain.models import (
    AgentProfile,
    KnowledgeBundle,
    KnowledgeFragment,
    LessonTask,
)


def _fragment(source_id: str, content: str, location: str = "") -> KnowledgeFragment:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return KnowledgeFragment(
        fragment_id=f"fragment-{digest[:12]}",
        source_id=source_id,
        source_version="live-engineering-v1.0",
        location=location,
        content=content,
        content_hash=digest,
    )


def _task_context(task: LessonTask) -> str:
    parts = [
        f"课程信息：{task.course_information}",
        f"学科/年级/主题：{task.subject}/{task.grade}/{task.topic}",
        f"课时：{task.duration_minutes} 分钟",
        f"教材内容：{task.textbook_content or '未提供'}",
        f"课程标准：{'；'.join(task.curriculum_standards) or '未提供'}",
        f"用户目标：{'；'.join(task.learning_objectives) or '未提供'}",
        f"学情：{task.student_profile or '未提供'}",
        f"课堂约束：{task.class_constraints}",
        f"可用资源：{'；'.join(task.available_resources) or '未提供'}",
    ]
    return "\n".join(parts)


_WRITER_RULES = """生成时始终锚定课程主题、年级、课时和学情。先明确可观察的学习目标及达成证据，
再组织与当前目标直接相关的教学事件；无需机械塞入所有教学法。每个步骤必须关联目标，写清教师行动、
学生活动、关键提问、形成性评价、设计意图和时间。步骤总时长应等于任务课时。引用只允许来自输入，
缺少正式课标原文时应保留输入中的限定说明。"""

_PEDAGOGY_RULES = """内部教学法审查关注学习如何发生：检查先备知识与认知进阶、支架逐步撤除、学生而非
教师的实质参与、课堂时间与资源可执行性、形成性反馈如何触发教师调控，以及基础支持与拓展任务。目标、
活动和评价之间的可追溯对应由 Alignment Critic 专门审查；教学法角色只在反馈机制或活动品质本身有问题时
提出意见。以上是工程审查框架，不替代正式专家评价。"""

_ALIGNMENT_RULES = """内部对齐审查采用目标—活动—评价一致性原则，并把课程依据、学习目标、教学步骤、
学生产出、评价任务和成功标准组织为可追溯证据链。结构关联只说明字段互相引用，不自动证明语义匹配；
必须检查活动要求的认知行为、产出以及评价证据是否真正对应目标层级。不得因个人偏好重设教学路线，不得
代替学科专家判断事实真伪。输入未提供正式课标时，不得补造课标编号或文本。以上是内部工程协议，不是
经过专家效度验证的正式量表。"""

_VALIDATION_RULES = """每条批评必须单独核验 grounded、relevant、actionable、conflict 四项。
只有有明确教案证据或输入依据、与当前任务相关、能落到具体修改、且不与更高优先级约束冲突时才 accept。
重复意见应 merge 到同批次一个已 accept 的 canonical critique；证据暂不足但值得保留才 defer；其余 reject。
不得补造新的批评，也不得直接修改教案。"""

_RUBRIC = """冻结八维内部量表（每维 0–10）：1 课程标准/目标一致性；2 学科知识准确性与适用条件；
3 教学逻辑与认知进阶；4 时间、资源和班额下的课堂可执行性；5 差异化支持；6 学生认知参与；
7 形成性与总结性评价设计；8 语言与结构格式。9–10 表示证据充分、约束完整且可直接试用；7–8.9 表示
基本可靠但仍有明确可改进处；5–6.9 表示关键环节薄弱；0–4.9 表示重大缺失或风险。评分是内部路由证据，
不是正式实验效果结论。高风险只标记学科事实错误、任务硬约束失败或会显著误导教学实施的问题。"""

_REWRITE_RULES = """只执行 validator 接受的意见，并对每个 critique_id 给出一对一修改记录。
保留 task_id、plan_id、元数据和未被意见触及的内容；优先局部修改，不无理由重写全文。若意见之间无法同时
满足，必须把对应 ID 放入 unresolved_critique_ids，不得偷偷采用 rejected、merged 或 deferred 意见。
修改后仍须满足结构引用完整、步骤时长合计正确等硬约束。"""


def _reference_profile() -> str:
    path = (
        Path(__file__).resolve().parents[3]
        / "data"
        / "reference_profiles"
        / "lesson_design_quality_v1_2.md"
    )
    return path.read_text(encoding="utf-8").strip()


def build_knowledge_bundle(
    profile: AgentProfile,
    task: LessonTask,
) -> KnowledgeBundle:
    fragments: list[KnowledgeFragment] = [
        _fragment("task_context", _task_context(task), "LessonTask")
    ]
    if profile.role == "design_architect":
        fragments.append(
            _fragment(
                "lesson_design_reference_v1_2",
                _reference_profile(),
                "derived_reference_profile",
            )
        )
    elif profile.role == "writer":
        fragments.append(
            _fragment("writer_design_rules", _WRITER_RULES, "engineering_protocol")
        )
    elif profile.role == "subject_critic":
        fragments.append(
            _fragment(
                "textbook",
                task.textbook_content or "任务未提供教材正文；只能核验输入中明确给出的学科信息。",
                "LessonTask.textbook_content",
            )
        )
    elif profile.role == "pedagogy_critic":
        fragments.append(
            _fragment("pedagogy_reference", _PEDAGOGY_RULES, "engineering_protocol")
        )
    elif profile.role == "alignment_critic":
        fragments.append(
            _fragment(
                "alignment_protocol_v0_1",
                _ALIGNMENT_RULES,
                "engineering_protocol",
            )
        )
    elif profile.role == "validator":
        fragments.append(
            _fragment("validation_rules", _VALIDATION_RULES, "engineering_protocol")
        )
    elif profile.role == "judge":
        fragments.append(_fragment("rubric_v0_1", _RUBRIC, "frozen_internal_rubric"))
    elif profile.role == "rewriter":
        fragments.append(
            _fragment("rewrite_rules", _REWRITE_RULES, "engineering_protocol")
        )
    else:
        raise ValueError(f"unsupported agent role: {profile.role}")

    if (
        "lesson_design_reference_v1_2" in profile.knowledge_source_ids
        and not any(
            item.source_id == "lesson_design_reference_v1_2" for item in fragments
        )
    ):
        fragments.append(
            _fragment(
                "lesson_design_reference_v1_2",
                _reference_profile(),
                "derived_reference_profile",
            )
        )

    actual_sources = [fragment.source_id for fragment in fragments]
    missing = set(actual_sources) - set(profile.knowledge_source_ids)
    if missing:
        raise ValueError(
            f"knowledge bundle contains undeclared profile sources: {sorted(missing)}"
        )
    return KnowledgeBundle(
        bundle_id=f"bundle-{task.task_id}-{profile.profile_id}",
        bundle_version="1.0",
        owner_profile_id=profile.profile_id,
        source_ids=list(profile.knowledge_source_ids),
        retrieved_fragments=fragments,
        retrieval_query=f"{task.subject} {task.grade} {task.topic} {profile.role}",
        retrieval_parameters={"mode": "versioned_registry", "top_k": len(fragments)},
        status="ok",
    )
