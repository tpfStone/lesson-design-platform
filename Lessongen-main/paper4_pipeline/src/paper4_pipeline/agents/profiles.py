"""Versioned role profiles for the real DeepSeek pipeline."""

from __future__ import annotations

from paper4_pipeline.domain.models import AgentProfile, ModelConfig, RubricDimension


def default_profile_registry(
    role_model_configs: dict[str, ModelConfig] | None = None,
) -> dict[str, AgentProfile]:
    configs = role_model_configs or {}

    def model(profile_id: str) -> ModelConfig:
        return configs.get(profile_id, ModelConfig())

    profiles = [
        AgentProfile(
            profile_id="design_architect_v0_1",
            profile_version="1.0",
            role="design_architect",
            expertise_scope=[
                "学科化教学构思",
                "候选学习路径比较",
                "核心问题与认知转变",
                "可直接使用的学习材料设计",
            ],
            knowledge_source_ids=["task_context", "lesson_design_reference_v1_2"],
            rubric_dimensions=list(RubricDimension),
            allowed_actions=["propose_distinct_designs", "select_design_direction"],
            forbidden_actions=[
                "invent_curriculum_sources",
                "copy_reference_branding",
                "write_final_lesson_plan",
                "change_task_identity",
            ],
            visible_state_fields=["task", "knowledge_bundle", "output_schema"],
            prompt_id="design_architect_prompt",
            prompt_version="1.0",
            model=model("design_architect_v0_1"),
        ),
        AgentProfile(
            profile_id="writer_v0_1",
            profile_version="1.0",
            role="writer",
            expertise_scope=[
                "课程任务锚定",
                "目标—活动—评价一致性",
                "学科教学知识整合",
                "可执行课堂流程",
            ],
            knowledge_source_ids=[
                "task_context",
                "writer_design_rules",
                "lesson_design_reference_v1_2",
            ],
            rubric_dimensions=list(RubricDimension),
            allowed_actions=["create_structured_draft", "map_objectives_to_evidence"],
            forbidden_actions=[
                "declare_final_pass",
                "change_task_identity",
                "invent_curriculum_sources",
                "change_rubric",
            ],
            visible_state_fields=["task", "knowledge_bundle", "output_schema"],
            prompt_id="writer_prompt",
            prompt_version="1.3",
            model=model("writer_v0_1"),
        ),
        AgentProfile(
            profile_id="subject_critic_v0_1",
            profile_version="1.0",
            role="subject_critic",
            expertise_scope=["学科事实与条件", "教材边界", "知识顺序", "常见误概念"],
            knowledge_source_ids=["task_context", "textbook"],
            rubric_dimensions=[RubricDimension.KNOWLEDGE_ACCURACY],
            allowed_actions=["propose_grounded_subject_critique"],
            forbidden_actions=[
                "rewrite_plan",
                "score_unrelated_dimensions",
                "route",
                "declare_final_pass",
            ],
            visible_state_fields=[
                "task",
                "current_version",
                "subject_knowledge",
                "prior_critiques",
            ],
            prompt_id="subject_critic_prompt",
            prompt_version="1.2",
            model=model("subject_critic_v0_1"),
        ),
        AgentProfile(
            profile_id="pedagogy_critic_v0_1",
            profile_version="1.0",
            role="pedagogy_critic",
            expertise_scope=[
                "认知进阶与支架",
                "学生参与",
                "形成性反馈与教师调控",
                "差异化教学",
                "课堂可执行性",
            ],
            knowledge_source_ids=[
                "task_context",
                "pedagogy_reference",
                "lesson_design_reference_v1_2",
            ],
            rubric_dimensions=[
                RubricDimension.TEACHING_LOGIC,
                RubricDimension.CLASSROOM_FEASIBILITY,
                RubricDimension.DIFFERENTIATED_INSTRUCTION,
                RubricDimension.STUDENT_ENGAGEMENT,
            ],
            allowed_actions=["propose_grounded_pedagogy_critique"],
            forbidden_actions=[
                "change_subject_facts",
                "rewrite_plan",
                "route",
                "declare_final_pass",
            ],
            visible_state_fields=[
                "task",
                "current_version",
                "pedagogy_knowledge",
                "prior_critiques",
            ],
            prompt_id="pedagogy_critic_prompt",
            prompt_version="1.3",
            model=model("pedagogy_critic_v0_1"),
        ),
        AgentProfile(
            profile_id="alignment_critic_v0_1",
            profile_version="1.0",
            role="alignment_critic",
            expertise_scope=[
                "课程依据—学习目标对齐",
                "目标可观察性与达成证据",
                "目标—活动—产出—评价证据链",
                "评价任务与成功标准对齐",
            ],
            knowledge_source_ids=["task_context", "alignment_protocol_v0_1"],
            rubric_dimensions=[
                RubricDimension.CURRICULUM_ALIGNMENT,
                RubricDimension.ASSESSMENT_DESIGN,
            ],
            allowed_actions=["propose_grounded_alignment_critique"],
            forbidden_actions=[
                "judge_subject_truth",
                "redesign_pedagogy_for_preference",
                "rewrite_plan",
                "score",
                "route",
                "declare_final_pass",
            ],
            visible_state_fields=[
                "task",
                "current_version",
                "alignment_knowledge",
                "alignment_audit",
                "prior_critiques",
            ],
            prompt_id="alignment_critic_prompt",
            prompt_version="1.1",
            model=model("alignment_critic_v0_1"),
        ),
        AgentProfile(
            profile_id="validator_v0_1",
            profile_version="1.0",
            role="validator",
            expertise_scope=["依据核验", "任务相关性", "可操作性", "冲突消解", "意见去重"],
            knowledge_source_ids=["task_context", "validation_rules"],
            rubric_dimensions=list(RubricDimension),
            allowed_actions=["accept", "reject", "merge", "defer"],
            forbidden_actions=["rewrite_plan", "invent_critique", "route", "change_rubric"],
            visible_state_fields=[
                "task",
                "current_version",
                "critique_batch",
                "validation_knowledge",
            ],
            prompt_id="validator_prompt",
            prompt_version="1.6",
            model=model("validator_v0_1"),
        ),
        AgentProfile(
            profile_id="judge_v0_1",
            profile_version="1.0",
            role="judge",
            expertise_scope=["八维内部质量评分", "硬约束风险汇总", "版本诊断"],
            knowledge_source_ids=[
                "task_context",
                "rubric_v0_1",
                "lesson_design_reference_v1_2",
            ],
            rubric_dimensions=list(RubricDimension),
            allowed_actions=["score_against_frozen_rubric", "recommend"],
            forbidden_actions=[
                "control_route",
                "rewrite_plan",
                "change_rubric",
                "claim_formal_effectiveness",
            ],
            visible_state_fields=[
                "task",
                "current_version",
                "rule_report",
                "rubric",
                "unresolved_issue_count",
            ],
            prompt_id="judge_prompt",
            prompt_version="1.3",
            model=model("judge_v0_1"),
        ),
        AgentProfile(
            profile_id="rewriter_v0_1",
            profile_version="1.0",
            role="rewriter",
            expertise_scope=["约束保持", "最小必要修订", "逐意见修改映射"],
            knowledge_source_ids=[
                "task_context",
                "rewrite_rules",
                "lesson_design_reference_v1_2",
            ],
            rubric_dimensions=list(RubricDimension),
            allowed_actions=["apply_accepted_critique", "declare_unresolved"],
            forbidden_actions=[
                "use_rejected_or_deferred_critique",
                "change_task_identity",
                "route",
                "change_rubric",
                "unexplained_full_rewrite",
            ],
            visible_state_fields=[
                "task",
                "current_version",
                "accepted_critiques",
                "rewrite_knowledge",
            ],
            prompt_id="rewriter_prompt",
            prompt_version="1.6",
            model=model("rewriter_v0_1"),
        ),
    ]
    return {profile.profile_id: profile for profile in profiles}


def validate_profile_references(
    profile_ids: list[str],
    registry: dict[str, AgentProfile] | None = None,
) -> None:
    available = registry or default_profile_registry()
    missing = sorted(set(profile_ids) - set(available))
    if missing:
        raise ValueError(f"unknown agent profile IDs: {missing}")
