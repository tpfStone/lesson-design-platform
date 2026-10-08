"""Evidence-based summary of an optimization run, never inferred from scores alone."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from paper4_pipeline.domain.models import (
    ExperimentConfig, LessonPlanDocument, LessonPlanVersion, PipelineResult, StopReason,
)


_IDENTITY_FIELDS = {"schema_version", "task_id", "plan_id", "template_id"}
_SECTION_LABELS = {
    "metadata": "课程信息", "design_thesis": "设计主张", "driving_question": "驱动问题",
    "learning_trajectory": "学习轨迹", "curriculum_standards": "课程标准",
    "content_analysis": "教学内容分析", "student_analysis": "学情分析",
    "learning_objectives": "学习目标", "key_points": "教学重点",
    "difficult_points": "教学难点", "teaching_strategy": "教学策略",
    "resources": "教学资源", "teaching_artifacts": "教学材料",
    "procedure_steps": "教学过程", "assessment_plan": "评价设计",
    "differentiation": "差异化支持", "homework": "作业",
    "board_design": "板书", "reflection": "反思", "references": "参考资料",
    "template_extensions": "扩展内容",
}


def _content(document: LessonPlanDocument) -> dict[str, Any]:
    data = document.model_dump(mode="json")
    return {key: value for key, value in data.items() if key not in _IDENTITY_FIELDS}


def content_hash(document: LessonPlanDocument) -> str:
    payload = json.dumps(_content(document), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def optimization_quality_gate(
    baseline: LessonPlanVersion,
    candidate: LessonPlanVersion,
    config: ExperimentConfig,
) -> dict[str, Any]:
    """Internal revision threshold; not a claim of classroom effectiveness.

    The absolute rubric target alone is insufficient: a revision must change
    teaching content, beat its own baseline, and avoid material regressions.
    Scores are one signal; a human or paired review still decides adoption.
    """
    before = baseline.internal_evaluation
    after = candidate.internal_evaluation
    changed = content_hash(baseline.document) != content_hash(candidate.document)
    score_gain = (
        round(after.overall_score - before.overall_score, 3)
        if before is not None and after is not None else None
    )
    dimension_drops: dict[str, float] = {}
    if before is not None and after is not None:
        old = before.rubric_scores.model_dump(mode="json")
        new = after.rubric_scores.model_dump(mode="json")
        dimension_drops = {
            key: round(old[key] - new[key], 3) for key in old
            if old[key] - new[key] > 0
        }
    hard_rules_ok = candidate.rule_check_report.passed
    no_high_risk = bool(after is not None and not after.high_risk_issue_ids and not after.regressions)
    absolute_ok = bool(
        after is not None
        and after.overall_score >= config.optimization_quality_threshold
        and min(after.rubric_scores.values_list()) >= config.critical_dimension_floor
    )
    relative_ok = bool(
        score_gain is not None
        and score_gain + 1e-9 >= config.optimization_min_score_gain
        and all(
            drop <= config.optimization_dimension_drop_tolerance + 1e-9
            for drop in dimension_drops.values()
        )
    )
    return {
        "passed": bool(changed and candidate.change_count > 0 and hard_rules_ok
                       and no_high_risk and absolute_ok and relative_ok),
        "content_changed": changed,
        "score_gain": score_gain,
        "dimension_drops": dimension_drops,
        "hard_rules_ok": hard_rules_ok,
        "no_high_risk": no_high_risk,
        "absolute_target_met": absolute_ok,
        "relative_target_met": relative_ok,
        "thresholds": {
            "overall": config.optimization_quality_threshold,
            "minimum_dimension": config.critical_dimension_floor,
            "minimum_gain": config.optimization_min_score_gain,
            "maximum_dimension_drop": config.optimization_dimension_drop_tolerance,
        },
        "note": "仅为内部修订门槛；不能替代教师判断或课堂效果实验。",
    }


def unselected_revised_candidate(result: PipelineResult) -> LessonPlanVersion | None:
    """Expose a safe edited candidate when stochastic ranking retains v0."""
    if not result.versions:
        return None
    baseline = min(result.versions, key=lambda item: (item.iteration, item.version_id))
    candidates = [
        version for version in result.versions
        if version.version_id != result.best_version_id
        and version.iteration > baseline.iteration
        and content_hash(version.document) != content_hash(baseline.document)
        and version.rule_check_report.passed
        and version.internal_evaluation is not None
        and not version.internal_evaluation.high_risk_issue_ids
        and not version.internal_evaluation.regressions
    ]
    return max(candidates, key=lambda item: (item.iteration, item.version_id)) if candidates else None


def _changed_sections(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"field": field, "label": _SECTION_LABELS.get(field, field),
         "before": before.get(field), "after": after.get(field)}
        for field in sorted(set(before) | set(after)) if before.get(field) != after.get(field)
    ]


def optimization_summary(result: PipelineResult) -> dict[str, Any]:
    """Compare the actually selected plan to v0 and describe the real review trail."""
    if not result.versions:
        raise ValueError("optimization summary requires a saved baseline")
    baseline = min(result.versions, key=lambda version: (version.iteration, version.version_id))
    selected = next(version for version in result.versions
                    if version.version_id == result.best_version_id)
    before = _content(baseline.document)
    after = _content(selected.document)
    sections = _changed_sections(before, after)
    candidate = unselected_revised_candidate(result)
    changed = bool(sections)
    decisions = {
        decision.critique_id: decision
        for batch in result.validation_batches
        for decision in batch.decisions
    }
    reviewed_issues = [
        {
            "critique_id": item.critique_id,
            "role": item.critic_profile_id or item.source.value,
            "target_path": item.target_path,
            "issue": item.issue,
            "suggestion": item.actionable_suggestion,
            "status": item.status.value,
            "decision": decisions[item.critique_id].decision.value
            if item.critique_id in decisions else None,
            "decision_reason": decisions[item.critique_id].reason
            if item.critique_id in decisions else None,
        }
        for item in result.critiques
    ]
    rounds = []
    for record in result.rewrite_records:
        rounds.append({
            "input_version_id": record.input_version_id,
            "output_version_id": record.output_version_id,
            "strategy": record.strategy,
            "accepted_count": len(record.accepted_critique_ids),
            "implemented_count": len(record.changes),
            "unresolved_count": len(record.unresolved_critique_ids),
            "unresolved_reasons": record.unresolved_reasons,
            "changes": [
                {"critique_id": change.critique_id,
                 "target_path": change.target_path,
                 "edited_paths": change.edited_paths,
                 "before_summary": change.before_summary,
                 "after_summary": change.after_summary}
                for change in record.changes
            ],
        })
    if not changed and result.stop_reason == StopReason.REWRITE_FAILED:
        outcome = "rewrite_failed"
        message = (
            "审查发现并接受了可执行意见，但改写阶段未能产生通过校验的版本；"
            "当前仅保留原稿，并非没有优化空间。"
        )
    elif changed:
        outcome = "changed"
        message = f"选中的教案相对原稿有 {len(sections)} 个内容栏目发生变化；仍需教师确认教学效果。"
    elif result.rewrite_records:
        outcome = "revisions_not_selected"
        message = "系统产生过修订候选稿，但最终交付内容与原稿一致；不能宣称本次有内容改进。"
    elif result.critiques:
        outcome = "reviewed_unchanged"
        message = "完成了审查，但未形成可交付的内容修改；本次交付仍是原稿。"
    else:
        outcome = "not_reviewed"
        message = "尚未进入完整审查与改写；本次交付仍是原稿。"
    baseline_score = (
        baseline.internal_evaluation.overall_score if baseline.internal_evaluation else None
    )
    selected_score = (
        selected.internal_evaluation.overall_score if selected.internal_evaluation else None
    )
    return {
        "outcome": outcome,
        "message": message,
        "baseline_version_id": baseline.version_id,
        "selected_version_id": selected.version_id,
        "baseline_content_hash": content_hash(baseline.document),
        "selected_content_hash": content_hash(selected.document),
        "content_changed": changed,
        "changed_section_count": len(sections),
        "changed_sections": sections,
        "unselected_candidate_version_id": candidate.version_id if candidate else None,
        "unselected_candidate_score": (
            candidate.internal_evaluation.overall_score if candidate and candidate.internal_evaluation
            else None
        ),
        "unselected_candidate_changed_sections": (
            _changed_sections(before, _content(candidate.document)) if candidate else []
        ),
        "baseline_score": baseline_score,
        "selected_score": selected_score,
        "score_delta": (
            round(selected_score - baseline_score, 3)
            if changed and baseline_score is not None and selected_score is not None
            else None
        ),
        "score_notice": "模型内部评分有波动；同稿分差不算优化，内容变化也不等于教学效果提升。",
        "critique_count": len(result.critiques),
        "reviewed_issues": reviewed_issues,
        "validation_batch_count": len(result.validation_batches),
        "rewrite_count": len(result.rewrite_records),
        "rounds": rounds,
        "stop_reason": result.stop_reason.value if result.stop_reason else None,
        "quality_gate": result.optimization_quality_gate,
        "pairwise_comparison": result.optimization_comparison,
    }
