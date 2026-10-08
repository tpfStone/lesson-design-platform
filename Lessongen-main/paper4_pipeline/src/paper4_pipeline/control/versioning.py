"""Deterministic best-version selection and stable content hashes."""

from __future__ import annotations

import hashlib
import json

from paper4_pipeline.domain.models import (
    ExperimentConfig,
    LessonPlanDocument,
    LessonPlanVersion,
    TaskMode,
    VersionSelection,
)
from paper4_pipeline.control.optimization import content_hash


def document_hash(document: LessonPlanDocument) -> str:
    payload = json.dumps(
        document.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _rank(version: LessonPlanVersion) -> tuple:
    """Rank an evaluated version, quality-first.

    Hard eliminations (rule failure, high-risk issues, regressions, missing
    evaluation) already removed unsafe versions in ``select_best_version``.
    Among the survivors the primary signal is judged quality, so an improved
    rewrite is never beaten by a raw draft merely because it carries a couple
    of still-open (non-high-risk) items. ``unresolved_issue_count`` remains a
    secondary tie-breaker *after* the scores, so an unresolved-heavy version
    still loses to an equal-scoring clean one.
    """
    report = version.internal_evaluation
    if report is None:
        return (-1, -999, -999, -999, -999, -999, -999, version.version_id)
    minimum_dimension = min(report.rubric_scores.values_list())
    return (
        -len(report.high_risk_issue_ids),
        report.overall_score,
        minimum_dimension,
        -report.unresolved_issue_count,
        -version.change_count,
        -version.estimated_cost,
        -version.iteration,
        version.version_id,
    )


def select_best_version(
    versions: list[LessonPlanVersion],
    config: ExperimentConfig,
    *,
    dedupe_equivalent_content: bool = False,
    task_mode: TaskMode = TaskMode.GENERATE,
) -> VersionSelection:
    """Choose the highest-quality safe version; never assume the last is the best."""

    if not versions:
        raise ValueError("at least one version is required")
    eliminated: dict[str, list[str]] = {}
    eligible: list[LessonPlanVersion] = []
    for version in versions:
        reasons: list[str] = []
        if not version.rule_check_report.passed:
            reasons.append("hard_rule_failure")
        if version.internal_evaluation is None:
            reasons.append("missing_internal_evaluation")
        if version.internal_evaluation and version.internal_evaluation.high_risk_issue_ids:
            reasons.append("high_risk_issue")
        if version.internal_evaluation and version.internal_evaluation.regressions:
            reasons.append("reported_regression")
        if reasons:
            eliminated[version.version_id] = reasons
        else:
            eligible.append(version)

    # A failed rewrite must not make the result unreturnable. If all versions
    # are ineligible, retain the earliest version only as an explicit
    # review-required fallback; it is not certified safe or complete.
    if not eligible:
        fallback = min(versions, key=lambda item: (item.iteration, item.version_id))
        return VersionSelection(
            selection_id=f"selection-{len(versions)}",
            selected_version_id=fallback.version_id,
            eligible_candidate_ids=[],
            eliminated_candidates=eliminated,
            requires_human=True,
        )

    if dedupe_equivalent_content:
        unique: list[LessonPlanVersion] = []
        seen_content: set[str] = set()
        for version in sorted(eligible, key=lambda item: (item.iteration, item.version_id)):
            digest = content_hash(version.document)
            if digest in seen_content:
                eliminated[version.version_id] = ["equivalent_content_re_evaluation"]
                continue
            seen_content.add(digest)
            unique.append(version)
        eligible = unique

    if task_mode == TaskMode.OPTIMIZE:
        baseline = min(versions, key=lambda item: (item.iteration, item.version_id))
        baseline_report = baseline.internal_evaluation
        baseline_scores = (
            baseline_report.rubric_scores.model_dump(mode="json")
            if baseline_report else None
        )
        revision_candidates: list[LessonPlanVersion] = []
        for version in eligible:
            if version.iteration <= baseline.iteration or version.change_count < 1:
                continue
            if content_hash(version.document) == content_hash(baseline.document):
                continue
            report = version.internal_evaluation
            assert report is not None
            # Open-issue counts are snapshots of *different* review histories:
            # v0 is evaluated before any critic, so zero is not evidence that
            # it is cleaner than v2. Compare only common frozen rubric values
            # and explicit safety checks when choosing a provisional revision.
            if baseline_report and (
                report.overall_score + config.epsilon < baseline_report.overall_score
                or any(
                    baseline_scores[key] - value
                    > config.optimization_dimension_drop_tolerance
                    for key, value in report.rubric_scores.model_dump(mode="json").items()
                )
            ):
                continue
            revision_candidates.append(version)
        if revision_candidates:
            highest_score = max(
                item.internal_evaluation.overall_score for item in revision_candidates
            )
            near_best = [
                item for item in revision_candidates
                if item.internal_evaluation.overall_score + config.epsilon >= highest_score
            ]
            winner = max(near_best, key=lambda item: (item.iteration, item.version_id))
            others = sorted(
                (item for item in eligible if item.version_id != winner.version_id),
                key=_rank, reverse=True,
            )
            return VersionSelection(
                selection_id=f"selection-{len(versions)}",
                selected_version_id=winner.version_id,
                eligible_candidate_ids=[winner.version_id, *(item.version_id for item in others)],
                eliminated_candidates=eliminated,
                ambiguous_candidate_ids=(
                    [baseline.version_id, winner.version_id]
                    if baseline.version_id in {item.version_id for item in eligible}
                    and baseline_report
                    and abs(winner.internal_evaluation.overall_score
                            - baseline_report.overall_score) <= config.epsilon
                    else []
                ),
                requires_human=True,
                selection_policy_version="optimization-revision-v1.0",
                selection_reason=(
                    "真实修改稿通过结构与风险筛查，且未低于原稿的内部评分容差；"
                    "作为待教师复核稿优先交付，不以审查前的零条意见判原稿更优。"
                ),
            )

    ordered = sorted(eligible, key=_rank, reverse=True)
    winner = ordered[0]
    ambiguous: list[str] = []
    if len(ordered) > 1:
        first = winner.internal_evaluation
        second = ordered[1].internal_evaluation
        assert first is not None and second is not None
        if (
            len(first.high_risk_issue_ids) == len(second.high_risk_issue_ids)
            and (
                dedupe_equivalent_content
                or first.unresolved_issue_count == second.unresolved_issue_count
            )
            and abs(first.overall_score - second.overall_score) <= config.epsilon
            and abs(
                min(first.rubric_scores.values_list())
                - min(second.rubric_scores.values_list())
            )
            <= config.epsilon
        ):
            ambiguous = [winner.version_id, ordered[1].version_id]
    return VersionSelection(
        selection_id=f"selection-{len(versions)}",
        selected_version_id=winner.version_id,
        eligible_candidate_ids=[item.version_id for item in ordered],
        eliminated_candidates=eliminated,
        ambiguous_candidate_ids=ambiguous,
        requires_human=bool(ambiguous),
    )
