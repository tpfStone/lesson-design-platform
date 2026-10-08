"""Pure routing policy: model opinions are evidence, never control flow."""

from __future__ import annotations

from paper4_pipeline.control.versioning import document_hash
from paper4_pipeline.control.optimization import optimization_quality_gate
from paper4_pipeline.domain.models import (
    CritiqueBatch,
    EvaluationReport,
    ExperimentConfig,
    LessonPlanVersion,
    RouteAction,
    RouteDecision,
    RuleCheckReport,
    StopReason,
    TokenUsage,
    TaskMode,
)


_PRIORITY = [
    StopReason.RUNTIME_ERROR,
    StopReason.VALIDATION_ERROR,
    StopReason.HUMAN_STOP,
    StopReason.REGRESSION_GUARD,
    StopReason.QUALITY_PASSED,
    StopReason.NO_ACTIONABLE_FEEDBACK,
    StopReason.OSCILLATION,
    StopReason.PLATEAU,
    StopReason.BUDGET_EXCEEDED,
    StopReason.MAX_ROUNDS,
]


def _primary(reasons: list[StopReason]) -> StopReason | None:
    return next((item for item in _PRIORITY if item in reasons), None)


def _plateau(score_deltas: list[float], config: ExperimentConfig) -> bool:
    if len(score_deltas) < config.patience:
        return False
    return all(abs(delta) < config.epsilon for delta in score_deltas[-config.patience :])


def _oscillation(versions: list[LessonPlanVersion]) -> bool:
    if len(versions) < 3:
        return False
    hashes = [document_hash(item.document) for item in versions[-3:]]
    return hashes[0] == hashes[2] and hashes[0] != hashes[1]


def route_after_evaluation(
    *,
    report: EvaluationReport,
    rule_report: RuleCheckReport,
    versions: list[LessonPlanVersion],
    config: ExperimentConfig,
    model_call_count: int,
    token_usage: TokenUsage,
    estimated_cost: float,
    score_deltas: list[float],
    required_next_model_calls: int,
    elapsed_seconds: float = 0.0,
    runtime_error: bool = False,
    validation_error: bool = False,
    human_stop: bool = False,
    require_initial_review: bool = False,
    task_mode: TaskMode = TaskMode.GENERATE,
) -> RouteDecision:
    reasons: list[StopReason] = []
    minimum_dimension = min(report.rubric_scores.values_list())
    if task_mode == TaskMode.OPTIMIZE:
        quality_passed = bool(
            not require_initial_review
            and optimization_quality_gate(versions[0], versions[-1], config)["passed"]
        )
    else:
        quality_passed = (
            not require_initial_review
            and rule_report.passed
            and not report.high_risk_issue_ids
            and report.overall_score >= config.quality_threshold
            and minimum_dimension >= config.critical_dimension_floor
        )
    if runtime_error:
        reasons.append(StopReason.RUNTIME_ERROR)
    if validation_error:
        reasons.append(StopReason.VALIDATION_ERROR)
    if human_stop:
        reasons.append(StopReason.HUMAN_STOP)
    if report.regressions:
        reasons.append(StopReason.REGRESSION_GUARD)
    if quality_passed:
        reasons.append(StopReason.QUALITY_PASSED)
    if _oscillation(versions):
        reasons.append(StopReason.OSCILLATION)
    # Identical Judge scores do not imply identical lesson-plan content. In
    # optimization the edited document, issue evidence and safety checks are
    # the progress signals; do not stop a real revision after only two rounds
    # because this noisy scalar happened not to move.
    if task_mode != TaskMode.OPTIMIZE and _plateau(score_deltas, config):
        reasons.append(StopReason.PLATEAU)
    current_iteration = versions[-1].iteration
    max_rounds_hit = current_iteration >= (
        config.optimization_max_rounds if task_mode == TaskMode.OPTIMIZE
        else config.max_rounds
    )
    # A review of v0 does not consume a rewrite round. Even max_rounds=0
    # must permit the promised initial independent review when affordable.
    if require_initial_review:
        max_rounds_hit = False
    # Separate resources already consumed from capacity needed only by a future
    # review cycle. Once max_rounds has independently ended the run, that future
    # cycle cannot happen, so its retry reserve must not masquerade as an
    # exhausted budget. Limits already reached remain budget reasons.
    actual_budget_hit = (
        model_call_count >= config.max_model_calls
        or token_usage.total_tokens >= config.max_total_tokens
        or estimated_cost >= config.max_estimated_cost
        or elapsed_seconds >= config.max_runtime_seconds
    )
    projected_call_budget_hit = (
        not max_rounds_hit
        and model_call_count + required_next_model_calls > config.max_model_calls
    )
    budget_hit = actual_budget_hit or projected_call_budget_hit
    if budget_hit:
        reasons.append(StopReason.BUDGET_EXCEEDED)
    if max_rounds_hit:
        reasons.append(StopReason.MAX_ROUNDS)

    if reasons:
        primary = _primary(reasons)
        if primary in {StopReason.RUNTIME_ERROR, StopReason.VALIDATION_ERROR}:
            status = RouteAction.FAIL
        elif primary == StopReason.REGRESSION_GUARD:
            status = RouteAction.ROLLBACK
        else:
            status = RouteAction.FINALIZE
        return RouteDecision(
            decision_id=f"route-eval-{current_iteration}",
            next_action=status,
            primary_reason=primary,
            triggered_reasons=reasons,
            explanation=f"程序化停止条件触发：{', '.join(r.value for r in reasons)}",
        )
    return RouteDecision(
        decision_id=f"route-eval-{current_iteration}",
        next_action=RouteAction.CONTINUE_REVIEW,
        triggered_reasons=[],
        explanation="质量门槛尚未满足，且预算允许继续批评。",
    )


def route_after_validation(
    *,
    critiques: CritiqueBatch,
    config: ExperimentConfig,
    model_call_count: int,
    token_usage: TokenUsage,
    estimated_cost: float,
    required_next_model_calls: int = 2,
    elapsed_seconds: float = 0.0,
    max_rounds_hit: bool = False,
) -> RouteDecision:
    accepted = [item for item in critiques.items if item.status.value == "accepted"]
    reasons: list[StopReason] = []
    if not accepted:
        reasons.append(StopReason.NO_ACTIONABLE_FEEDBACK)
    if max_rounds_hit and accepted:
        reasons.append(StopReason.MAX_ROUNDS)
    if not max_rounds_hit and (
        model_call_count + required_next_model_calls > config.max_model_calls
        or token_usage.total_tokens >= config.max_total_tokens
        or estimated_cost >= config.max_estimated_cost
        or elapsed_seconds >= config.max_runtime_seconds
    ):
        reasons.append(StopReason.BUDGET_EXCEEDED)
    if reasons:
        return RouteDecision(
            decision_id=f"route-validation-{critiques.round_index}",
            next_action=RouteAction.FINALIZE,
            primary_reason=_primary(reasons),
            triggered_reasons=reasons,
            explanation=f"无法进入改写：{', '.join(r.value for r in reasons)}",
        )
    return RouteDecision(
        decision_id=f"route-validation-{critiques.round_index}",
        next_action=RouteAction.REWRITE,
        explanation=f"{len(accepted)} 条已验证意见进入最小必要改写。",
    )
