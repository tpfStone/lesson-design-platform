"""Critique validation and lifecycle transitions."""

from __future__ import annotations

from collections import Counter

from paper4_pipeline.domain.models import (
    CritiqueBatch,
    CritiqueItem,
    CritiqueStatus,
    CritiqueTransition,
    LessonPlanDocument,
    LessonTask,
    RewriteOutcome,
    RubricDimension,
    ValidationBatch,
    ValidationDecision,
    ValidationDecisionKind,
)


_ALLOWED_TRANSITIONS: dict[CritiqueStatus, set[CritiqueStatus]] = {
    CritiqueStatus.PROPOSED: {
        CritiqueStatus.ACCEPTED,
        CritiqueStatus.REJECTED,
        CritiqueStatus.MERGED,
        CritiqueStatus.DEFERRED,
    },
    CritiqueStatus.ACCEPTED: {
        CritiqueStatus.IMPLEMENTED,
        CritiqueStatus.PARTIALLY_IMPLEMENTED,
        CritiqueStatus.UNRESOLVED,
    },
    CritiqueStatus.DEFERRED: {CritiqueStatus.REOPENED},
    CritiqueStatus.IMPLEMENTED: {
        CritiqueStatus.VERIFIED_FIXED,
        CritiqueStatus.REOPENED,
        CritiqueStatus.UNRESOLVED,
        CritiqueStatus.REGRESSION,
    },
    CritiqueStatus.PARTIALLY_IMPLEMENTED: {
        CritiqueStatus.VERIFIED_FIXED,
        CritiqueStatus.REOPENED,
        CritiqueStatus.UNRESOLVED,
        CritiqueStatus.REGRESSION,
    },
    CritiqueStatus.UNRESOLVED: {
        CritiqueStatus.REOPENED,
        CritiqueStatus.DEFERRED,
    },
    CritiqueStatus.VERIFIED_FIXED: {
        CritiqueStatus.REOPENED,
        CritiqueStatus.REGRESSION,
    },
    # A reopened cap-deferred item may be superseded: a later critic can
    # re-propose the same issue, and the Validator then keeps the fresh
    # proposal as canonical and MERGEs the older reopened item into it.
    CritiqueStatus.REOPENED: {
        CritiqueStatus.ACCEPTED,
        CritiqueStatus.REJECTED,
        CritiqueStatus.MERGED,
        CritiqueStatus.DEFERRED,
    },
    CritiqueStatus.REJECTED: set(),
    CritiqueStatus.MERGED: set(),
    CritiqueStatus.REGRESSION: {CritiqueStatus.REOPENED},
}


# The Validator prompt says a rewrite round should stay focused on the few
# highest-leverage opinions.  That intent is only trustworthy if it is also a
# structural limit: opinion is evidence, never control flow, so surplus ACCEPT
# decisions are deterministically deferred instead of being forwarded to the
# Rewriter.  An ACCEPTED critique cannot later be demoted (state transitions do
# not allow it), so the cap must be applied at validation time, on PROPOSED
# items, before any transition is recorded.
DEFAULT_MAX_ACCEPTS_PER_ROUND = 5


_CURRICULUM_EVIDENCE_TERMS = (
    "curriculum standard",
    "standard_ref",
    "standard ref",
    "课程标准",
    "课标",
    "课程依据",
)

_IMMUTABLE_IDENTITY_TERMS = (
    "/metadata",
    "metadata.subject",
    "metadata.grade",
    "metadata.topic",
    "metadata.duration",
    "修改科目",
    "更改科目",
    "修改年级",
    "更改年级",
    "修改课题",
    "更改课题",
)


def _requires_unavailable_curriculum_evidence(
    critique: CritiqueItem,
    task: LessonTask,
) -> bool:
    """Return whether a critique asks the rewrite to invent absent standards."""

    if task.curriculum_standards:
        return False
    if critique.dimension != RubricDimension.CURRICULUM_ALIGNMENT:
        return False
    if not critique.target_path.startswith(
        ("/learning_objectives", "/curriculum_standards")
    ):
        return False
    description = " ".join(
        (
            critique.issue_code,
            critique.issue,
            critique.evidence,
            critique.actionable_suggestion,
        )
    ).lower()
    return any(term in description for term in _CURRICULUM_EVIDENCE_TERMS)


def _requires_immutable_identity_edit(critique: CritiqueItem) -> bool:
    """Return whether an opinion asks Rewriter to mutate task identity."""

    suggestion = critique.actionable_suggestion.lower()
    return any(term in suggestion for term in _IMMUTABLE_IDENTITY_TERMS)


def enforce_task_evidence_constraints(
    critiques: CritiqueBatch,
    decisions: list[ValidationDecision],
    task: LessonTask,
) -> list[ValidationDecision]:
    """Downgrade edits whose required authoritative evidence is unavailable.

    This post-Validator gate only rejects; it never promotes a model decision.
    A placeholder cannot establish real curriculum alignment, and allowing one
    into Rewriter creates an impossible choose-between-fabrication-and-failure
    loop.  MERGEs targeting a blocked canonical are rejected with it.
    """

    critique_by_id = {item.critique_id: item for item in critiques.items}
    evidence_blocked = {
        decision.critique_id
        for decision in decisions
        if decision.decision == ValidationDecisionKind.ACCEPT
        and decision.critique_id in critique_by_id
        and _requires_unavailable_curriculum_evidence(
            critique_by_id[decision.critique_id], task
        )
    }
    identity_blocked = {
        decision.critique_id
        for decision in decisions
        if decision.decision == ValidationDecisionKind.ACCEPT
        and decision.critique_id in critique_by_id
        and _requires_immutable_identity_edit(critique_by_id[decision.critique_id])
    }
    blocked = evidence_blocked | identity_blocked
    if not blocked:
        return decisions

    guarded: list[ValidationDecision] = []
    for decision in decisions:
        blocked_merge = (
            decision.decision == ValidationDecisionKind.MERGE
            and decision.canonical_critique_id in blocked
        )
        if decision.critique_id not in blocked and not blocked_merge:
            guarded.append(decision)
            continue
        payload = decision.model_dump(mode="python")
        if decision.critique_id in identity_blocked or (
            blocked_merge and decision.canonical_critique_id in identity_blocked
        ):
            reason = (
                "程序身份门禁：科目、年级、课题和课时属于用户确认的任务身份，"
                "Rewriter 无权修改；请修正提交表单后重新优化。"
            )
        else:
            reason = (
                "程序证据门禁：任务未提供课程标准，且系统禁止补造课标条款或 "
                "standard_refs；该输入缺口不能由 Rewriter 解决，请补充课标后重跑。"
            )
        payload.update(
            {
                "decision": ValidationDecisionKind.REJECT,
                "actionable": False,
                "conflict": True,
                "canonical_critique_id": "",
                "reason": reason,
            }
        )
        guarded.append(ValidationDecision.model_validate(payload))
    return guarded


def _require_unique_critique_ids(
    items: list[CritiqueItem],
    *,
    label: str,
) -> None:
    """Reject silently corrupted batches before lifecycle updates lose evidence."""

    counts = Counter(item.critique_id for item in items)
    duplicates = sorted(item_id for item_id, count in counts.items() if count != 1)
    if duplicates:
        raise ValueError(f"duplicate critique ids in {label}: {duplicates}")


def _validated_batch_copy(
    batch: CritiqueBatch,
    *,
    items: list[CritiqueItem],
) -> CritiqueBatch:
    """Copy a batch through Pydantic validation instead of bypassing invariants."""

    payload = batch.model_dump(mode="python")
    payload["items"] = items
    return CritiqueBatch.model_validate(payload)


def _cap_reason(max_accepts: int) -> str:
    return (
        f"每轮至多接受 {max_accepts} 条最高杠杆意见；其余经核验的真实意见"
        "顺延至后续轮次（defer），并非否定其价值。"
    )


def _demote_to_defer(decision: ValidationDecision, reason: str) -> ValidationDecision:
    payload = decision.model_dump(mode="python")
    payload.update(
        {
            "decision": ValidationDecisionKind.DEFER,
            "canonical_critique_id": "",
            "reason": reason,
        }
    )
    return ValidationDecision.model_validate(payload)


def enforce_acceptance_cap(
    decisions: list[ValidationDecision],
    *,
    max_accepts: int = DEFAULT_MAX_ACCEPTS_PER_ROUND,
    priority_critique_ids: set[str] | None = None,
) -> list[ValidationDecision]:
    """Defer surplus ACCEPT decisions so one rewrite round stays focused.

    Accepted canonicals referenced by MERGE decisions are anchors and are kept
    ahead of un-anchored accepts; any MERGE whose canonical is deferred is
    deferred with it, preserving the ``merge target must be accepted``
    invariant inside the same batch.
    """

    if max_accepts is None or not decisions:
        return decisions
    accepts = [
        (index, decision)
        for index, decision in enumerate(decisions)
        if decision.decision == ValidationDecisionKind.ACCEPT
    ]
    if len(accepts) <= max_accepts:
        return decisions
    protected = {
        decision.canonical_critique_id
        for decision in decisions
        if decision.decision == ValidationDecisionKind.MERGE
    }
    priority_critique_ids = priority_critique_ids or set()
    ordered = sorted(
        accepts,
        key=lambda item: (
            0 if item[1].critique_id in protected else 1,
            0 if item[1].critique_id in priority_critique_ids else 1,
            -item[1].priority,
            item[0],
        ),
    )
    kept = {decision.critique_id for _, decision in ordered[:max_accepts]}
    reason = _cap_reason(max_accepts)
    capped: list[ValidationDecision] = []
    for decision in decisions:
        if decision.decision == ValidationDecisionKind.ACCEPT:
            if decision.critique_id not in kept:
                capped.append(_demote_to_defer(decision, reason))
            else:
                capped.append(decision)
        elif (
            decision.decision == ValidationDecisionKind.MERGE
            and decision.canonical_critique_id not in kept
        ):
            capped.append(_demote_to_defer(decision, reason))
        else:
            capped.append(decision)
    return capped


def transition_critique(
    critique: CritiqueItem,
    to_status: CritiqueStatus,
    round_index: int,
    version_id: str = "",
    note: str = "",
) -> CritiqueItem:
    """Return a new critique with an append-only, validated transition."""

    if to_status not in _ALLOWED_TRANSITIONS[critique.status]:
        raise ValueError(
            f"illegal critique transition: {critique.status.value} -> "
            f"{to_status.value}"
        )
    transition = CritiqueTransition(
        from_status=critique.status,
        to_status=to_status,
        round_index=round_index,
        version_id=version_id,
        note=note,
    )
    updates: dict = {
        "status": to_status,
        "history": [*critique.history, transition],
    }
    if to_status in {
        CritiqueStatus.ACCEPTED,
        CritiqueStatus.REJECTED,
        CritiqueStatus.MERGED,
        CritiqueStatus.DEFERRED,
    }:
        updates["validated_in_round"] = round_index
    if to_status in {
        CritiqueStatus.IMPLEMENTED,
        CritiqueStatus.PARTIALLY_IMPLEMENTED,
    }:
        updates["implemented_in_version_id"] = version_id
    if to_status in {
        CritiqueStatus.VERIFIED_FIXED,
        CritiqueStatus.REOPENED,
        CritiqueStatus.REGRESSION,
    }:
        updates["verified_in_round"] = round_index
    payload = critique.model_dump(mode="python")
    payload.update(updates)
    return CritiqueItem.model_validate(payload)


def apply_validation(
    critiques: CritiqueBatch,
    validation: ValidationBatch,
) -> CritiqueBatch:
    """Apply one Validator decision to every proposed or reopened critique."""

    _require_unique_critique_ids(critiques.items, label="validation input batch")
    if validation.critique_batch_id != critiques.batch_id:
        raise ValueError("validation batch references a different critique batch")
    if validation.round_index != critiques.round_index:
        raise ValueError("validation and critique rounds must match")
    critique_ids = {item.critique_id for item in critiques.items}
    decision_ids = [item.critique_id for item in validation.decisions]
    counts = Counter(decision_ids)
    duplicates = sorted(item_id for item_id, count in counts.items() if count != 1)
    unknown = sorted(set(decision_ids) - critique_ids)
    missing = sorted(critique_ids - set(decision_ids))
    if duplicates or unknown or missing:
        raise ValueError(
            "invalid validation coverage: "
            f"duplicates={duplicates}, unknown={unknown}, missing={missing}"
        )
    decisions = {item.critique_id: item for item in validation.decisions}
    accepted_ids = sorted(
        key for key, value in decisions.items()
        if value.decision == ValidationDecisionKind.ACCEPT
    )
    for decision in validation.decisions:
        if decision.decision == ValidationDecisionKind.MERGE:
            if decision.canonical_critique_id not in critique_ids:
                raise ValueError(
                    f"critique {decision.critique_id!r} targets "
                    f"{decision.canonical_critique_id!r} for merge, but that ID "
                    "does not exist in this critique batch. "
                    f"Available IDs: {sorted(critique_ids)}"
                )
            target_decision = decisions.get(decision.canonical_critique_id)
            if target_decision is None or target_decision.decision != ValidationDecisionKind.ACCEPT:
                target_kind = target_decision.decision.value if target_decision else "missing"
                raise ValueError(
                    f"critique {decision.critique_id!r} targets "
                    f"{decision.canonical_critique_id!r} for merge, but that target "
                    f"is {target_kind!r}; a merge target must be accepted in the "
                    "same batch. Current accepted IDs: "
                    f"{accepted_ids}. Choose an accepted target or give this "
                    "critique its own accept/reject/defer decision."
                )
    status_by_kind = {
        ValidationDecisionKind.ACCEPT: CritiqueStatus.ACCEPTED,
        ValidationDecisionKind.REJECT: CritiqueStatus.REJECTED,
        ValidationDecisionKind.MERGE: CritiqueStatus.MERGED,
        ValidationDecisionKind.DEFER: CritiqueStatus.DEFERRED,
    }
    updated: list[CritiqueItem] = []
    for critique in critiques.items:
        decision = decisions[critique.critique_id]
        item = transition_critique(
            critique,
            status_by_kind[decision.decision],
            round_index=validation.round_index,
            note=decision.reason,
        )
        if decision.decision == ValidationDecisionKind.MERGE:
            payload = item.model_dump(mode="python")
            payload["canonical_critique_id"] = decision.canonical_critique_id
            item = CritiqueItem.model_validate(payload)
        updated.append(item)
    return _validated_batch_copy(critiques, items=updated)


def actionable_critiques(batch: CritiqueBatch) -> list[CritiqueItem]:
    """Only accepted canonical critiques may reach the Rewriter."""

    _require_unique_critique_ids(batch.items, label="actionable critique batch")
    return [item for item in batch.items if item.status == CritiqueStatus.ACCEPTED]


def apply_rewrite_outcome(
    batch: CritiqueBatch,
    outcome: RewriteOutcome,
    round_index: int,
    output_version_id: str,
) -> CritiqueBatch:
    """Map every accepted critique to the Rewriter's declared outcome."""

    _require_unique_critique_ids(batch.items, label="rewrite input batch")
    accepted = {
        item.critique_id for item in batch.items if item.status == CritiqueStatus.ACCEPTED
    }
    changes = {item.critique_id: item for item in outcome.changes}
    unknown = sorted(
        (set(changes) | set(outcome.unresolved_critique_ids)) - accepted
    )
    missing = sorted(accepted - set(changes) - set(outcome.unresolved_critique_ids))
    if unknown or missing:
        raise ValueError(
            f"invalid rewrite mapping: unknown={unknown}, missing={missing}"
        )
    updated: list[CritiqueItem] = []
    for critique in batch.items:
        if critique.critique_id not in accepted:
            updated.append(critique)
            continue
        if critique.critique_id in outcome.unresolved_critique_ids:
            status = CritiqueStatus.UNRESOLVED
            note = outcome.unresolved_reasons.get(
                critique.critique_id,
                "rewriter could not implement this accepted critique",
            )
        else:
            change = changes[critique.critique_id]
            status = {
                "implemented": CritiqueStatus.IMPLEMENTED,
                "partially_implemented": CritiqueStatus.PARTIALLY_IMPLEMENTED,
            }[change.implementation_status]
            note = change.after_summary
        updated.append(
            transition_critique(
                critique,
                status,
                round_index=round_index,
                version_id=output_version_id,
                note=note,
            )
        )
    return _validated_batch_copy(batch, items=updated)


def merge_critique_history(
    history: list[CritiqueItem],
    updated_batch: CritiqueBatch,
) -> list[CritiqueItem]:
    """Replace known items and append new items without changing order."""

    _require_unique_critique_ids(history, label="critique history")
    _require_unique_critique_ids(updated_batch.items, label="updated critique batch")
    replacements = {item.critique_id: item for item in updated_batch.items}
    merged = [replacements.pop(item.critique_id, item) for item in history]
    merged.extend(replacements.values())
    return merged


# The acceptance cap promises surplus ACCEPT opinions "顺延至后续轮次 (defer)",
# not that they are dismissed. A carried opinion must be revalidated against the
# newer document: it is reopened before Validator, never accepted inside Rewriter.
DEFAULT_REOPEN_DEFERRED_PER_ROUND = 3
_CAP_DEFER_REASON_MARKER = "每轮至多接受"


def _is_cap_deferred(item: CritiqueItem, *, before_round: int) -> bool:
    if item.status != CritiqueStatus.DEFERRED:
        return False
    if any(transition.to_status == CritiqueStatus.REOPENED for transition in item.history):
        return False
    return any(
        transition.to_status == CritiqueStatus.DEFERRED
        and transition.round_index < before_round
        and transition.note.startswith(_CAP_DEFER_REASON_MARKER)
        for transition in item.history
    )


def reopen_cap_deferred_for_validation(
    history: list[CritiqueItem],
    *,
    round_index: int,
    version_id: str,
    per_round: int = DEFAULT_REOPEN_DEFERRED_PER_ROUND,
    exclude_ids: set[str] | None = None,
) -> tuple[list[CritiqueItem], list[CritiqueItem]]:
    """Reopen older cap-deferred critiques for current-version validation.

    Same-round deferrals are never reopened. Reopened items join the next
    Validator batch, where they may be accepted, rejected, merged, or deferred
    against the newer document. This prevents stale opinions from bypassing
    validation and keeps the total acceptance cap effective.
    """

    _require_unique_critique_ids(history, label="deferred critique history")
    if per_round < 0:
        raise ValueError("per_round must be non-negative")
    excluded = exclude_ids or set()
    eligible = sorted(
        (
            item
            for item in history
            if item.critique_id not in excluded
            and _is_cap_deferred(item, before_round=round_index)
        ),
        key=lambda item: (item.introduced_in_round, item.critique_id),
    )[:per_round]
    if not eligible:
        return history, []
    replacements: dict[str, CritiqueItem] = {}
    reopened_items: list[CritiqueItem] = []
    for item in eligible:
        reopened = transition_critique(
            item,
            CritiqueStatus.REOPENED,
            round_index=round_index,
            version_id=version_id,
            note="cap-deferred opinion reopened for current-version validation",
        )
        replacements[item.critique_id] = reopened
        reopened_items.append(reopened)
    updated = [replacements.pop(item.critique_id, item) for item in history]
    updated.extend(replacements.values())
    return updated, reopened_items


_DETERMINISTIC_ISSUE_CODES = frozenset(
    {
        "missing_differentiation",
        "objective_no_evidence",
        "step_no_assessment",
        "missing_misconception",
    }
)


def _path_segments(target_path: str) -> list[str]:
    return [part for part in target_path.split("/") if part]


def _locate_element(values: list[object], raw: str) -> int | None:
    """Resolve one path segment to a list index.

    A segment may be the object's own id (``/procedure_steps/step-2`` as the
    Paper#3 adapter emits) or a zero-based list index (as live critics emit,
    e.g. ``/learning_objectives/1``).  Return ``None`` when neither resolves,
    so callers can treat the location as unverifiable instead of guessing.
    """

    for index, value in enumerate(values):
        candidate = getattr(value, "objective_id", None) or getattr(
            value, "step_id", None
        )
        if candidate is not None and candidate == raw:
            return index
    try:
        index = int(raw)
    except (TypeError, ValueError):
        return None
    return index if 0 <= index < len(values) else None


def _semantic_resolution(
    document: LessonPlanDocument,
    critique: CritiqueItem,
) -> bool | None:
    """Deterministic tri-state check for a fixed set of engineering issue codes.

    ``True``  -> the addressed element is positively fixed.
    ``False`` -> the addressed element is located and still failing.
    ``None``  -> the code is not deterministically checkable, or the addressed
                 element cannot be reliably located; semantic quality then
                 belongs to the independent Judge, not to a string guess.
    """

    code = critique.issue_code
    if code == "missing_differentiation":
        return bool(document.differentiation.strip())
    if code == "objective_no_evidence":
        parts = _path_segments(critique.target_path)
        if len(parts) < 2 or parts[0] != "learning_objectives":
            return None
        index = _locate_element(document.learning_objectives, parts[1])
        if index is None:
            return None
        return bool(
            document.learning_objectives[index].evidence_of_achievement.strip()
        )
    if code == "step_no_assessment":
        parts = _path_segments(critique.target_path)
        if len(parts) < 2 or parts[0] != "procedure_steps":
            return None
        index = _locate_element(document.procedure_steps, parts[1])
        if index is None:
            return None
        return bool(document.procedure_steps[index].assessment.strip())
    if code == "missing_misconception":
        parts = _path_segments(critique.target_path)
        if len(parts) < 4 or parts[0] != "procedure_steps" or parts[2] != "questions":
            return None
        step_index = _locate_element(document.procedure_steps, parts[1])
        if step_index is None:
            return None
        try:
            question_index = int(parts[3])
        except ValueError:
            return None
        step = document.procedure_steps[step_index]
        if not (0 <= question_index < len(step.questions)):
            return None
        return bool(step.questions[question_index].possible_misconceptions)
    return None


# Top-level content fields whose presence (non-empty) is a hard contract the
# Rewriter can satisfy by supplying content.  Presence probing is deliberately
# limited to these document-level fields when the critique path addresses the
# field directly: element-level quality is left to independent review, and a
# critique pointing at specific nested content can never be reduced to "was the
# top field empty".
_PRESENCE_FIELDS = frozenset(
    {
        "design_thesis",
        "driving_question",
        "content_analysis",
        "student_analysis",
        "teaching_strategy",
        "curriculum_standards",
        "key_points",
        "difficult_points",
        "assessment_plan",
        "differentiation",
        "homework",
        "board_design",
        "reflection",
        "references",
        "learning_trajectory",
        "learning_objectives",
        "procedure_steps",
        "resources",
        "teaching_artifacts",
    }
)

# Words that indicate the critique's *defect* is that content is absent (read
# from issue/evidence/code/location -- where the problem is described, never
# from the suggested fix, which naturally talks about adding things).
_MISSING_PRESENCE_MARKERS = (
    "为空",
    "是空的",
    "仍是空",
    "仍为空",
    "空数组",
    "空列表",
    "空字段",
    "空白",
    "没有任何内容",
    "没有内容",
    "无内容",
    "缺少",
    "缺失",
    "未提供",
    "未给出",
    "未包含",
    "未写",
    "没有提供",
    "没有给出",
    "没有写",
    "漏掉",
    "遗漏",
    "missing",
    "absent",
    "not provided",
    "empty",
)


def _suggests_missing_content(critique: CritiqueItem) -> bool:
    text = " ".join(
        item
        for item in (
            critique.issue,
            critique.evidence,
            critique.issue_code,
            critique.lesson_location,
        )
        if item
    )
    lowered = text.lower()
    return any(marker in lowered for marker in _MISSING_PRESENCE_MARKERS)


def _field_is_empty(value: object) -> bool | None:
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return not value
    return None


def _presence_resolution(
    document: LessonPlanDocument,
    critique: CritiqueItem,
) -> bool | None:
    """Tri-state probe for "the addressed content field is still empty".

    ``True``  -> the critique reads as a missing-content complaint, the target
                 path addresses a known top-level field directly, and that
                 field is still empty.
    ``False`` -> same shape, but the field now holds content.
    ``None``  -> not a probeable shape (nested path, unknown field, or the text
                 does not claim absence); callers must not guess.
    """

    segments = _path_segments(critique.target_path)
    if len(segments) != 1:
        return None
    field = segments[0]
    if field not in _PRESENCE_FIELDS:
        return None
    if not _suggests_missing_content(critique):
        return None
    empty = _field_is_empty(getattr(document, field, None))
    if empty is None:
        return None
    return empty


def critique_is_resolved(
    document: LessonPlanDocument,
    critique: CritiqueItem,
) -> bool:
    """True only when the fix is positively confirmed by a deterministic check."""

    return _semantic_resolution(document, critique) is True


def verify_rewrite(
    batch: CritiqueBatch,
    document: LessonPlanDocument,
    round_index: int,
    version_id: str,
) -> CritiqueBatch:
    _require_unique_critique_ids(batch.items, label="verification input batch")
    updated: list[CritiqueItem] = []
    for critique in batch.items:
        if critique.status not in {
            CritiqueStatus.IMPLEMENTED,
            CritiqueStatus.PARTIALLY_IMPLEMENTED,
        }:
            updated.append(critique)
            continue
        # A change mapping proves that the Rewriter attempted a change; it does
        # not prove that an open-ended semantic issue is fixed.  Deterministic
        # issues can be promoted to VERIFIED_FIXED (or reopened as unresolved).
        # Other issues remain IMPLEMENTED/PARTIALLY_IMPLEMENTED until the next
        # independent review round provides new evidence.  This prevents the
        # system from falsely certifying its own prose claims.
        if critique.issue_code in _DETERMINISTIC_ISSUE_CODES:
            resolution = _semantic_resolution(document, critique)
            if resolution is True:
                target = CritiqueStatus.VERIFIED_FIXED
                note = "deterministic semantic verification"
            elif resolution is False:
                target = CritiqueStatus.UNRESOLVED
                note = "deterministic verification found the issue still present"
            else:
                target = critique.status
                note = (
                    "rewrite recorded; semantic fix awaits independent review "
                    "evidence"
                )
        elif _presence_resolution(document, critique) is True:
            # A rewrite claimed an accepted missing-content critique was
            # implemented, yet the addressed top-level field is still empty.
            # That is an honest UNRESOLVED -- the change mapping was a lie --
            # not a silent pass.  The probe never runs in the other direction:
            # content presence does not prove the critique was satisfied, so it
            # never certifies (VERIFIED_FIXED stays deterministic-only).
            target = CritiqueStatus.UNRESOLVED
            note = "presence probe: addressed field is still empty"
        else:
            target = critique.status
            note = "rewrite recorded; semantic fix awaits independent review evidence"
        if target == critique.status:
            updated.append(critique)
            continue
        updated.append(
            transition_critique(
                critique,
                target,
                round_index=round_index,
                version_id=version_id,
                note=note,
            )
        )
    return _validated_batch_copy(batch, items=updated)


def detect_regressions(
    history: list[CritiqueItem],
    document: LessonPlanDocument,
    round_index: int,
    version_id: str,
) -> list[CritiqueItem]:
    updated: list[CritiqueItem] = []
    for critique in history:
        # Only a positively re-confirmed failure counts as a regression.  A
        # contract-verified (non-deterministic) fix cannot be declared broken
        # again by a string parse, and an unlocatable target is left for the
        # Judge rather than spuriously reopened.
        regressed = (
            critique.status == CritiqueStatus.VERIFIED_FIXED
            and critique.issue_code in _DETERMINISTIC_ISSUE_CODES
            and _semantic_resolution(document, critique) is False
        )
        if regressed:
            updated.append(
                transition_critique(
                    critique,
                    CritiqueStatus.REGRESSION,
                    round_index=round_index,
                    version_id=version_id,
                    note="previously fixed issue reappeared",
                )
            )
        else:
            updated.append(critique)
    return updated
