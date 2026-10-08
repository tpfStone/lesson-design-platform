"""Optimization-only, order-balanced comparison of two lesson-plan versions.

This is evidence for delivery, not the eight-dimension Judge and not a proof
of classroom effectiveness. Both model calls are single-attempt and small-
output. Failure of either call is an explicit uncertain result.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from paper4_pipeline.agents.prompts import PromptSpec, default_prompt_root
from paper4_pipeline.agents.protocols import AgentCallMetadata, AgentOutput
from paper4_pipeline.domain.models import (
    LessonPlanVersion, LessonTask, StrictModel, TokenUsage,
)
from paper4_pipeline.providers.openai_compatible import (
    OpenAICompatibleProvider, ProviderInvocationError,
)


_CONTENT_FIELDS = (
    "design_thesis", "driving_question", "learning_trajectory",
    "curriculum_standards", "content_analysis", "student_analysis",
    "learning_objectives", "key_points", "difficult_points",
    "teaching_strategy", "resources", "teaching_artifacts",
    "procedure_steps", "assessment_plan", "differentiation", "homework",
    "board_design", "reflection", "references", "template_extensions",
)
_MAX_PAYLOAD_CHARACTERS = 70_000


class PairwiseVote(StrictModel):
    """One blinded A/B assessment. A/B are deliberately not version labels."""

    preferred: Literal["A", "B", "tie", "uncertain"]
    substantive_progress: bool
    target_issue_progress: Literal["improved", "unchanged", "worse", "uncertain"]
    regression_flags: list[str] = Field(default_factory=list, max_length=4)
    evidence: list[str] = Field(default_factory=list, max_length=3)
    rationale: str = Field(min_length=1, max_length=500)


class NormalizedVote(StrictModel):
    order: Literal["baseline_first", "candidate_first"]
    preference: Literal["candidate", "baseline", "uncertain"]
    substantive_progress: bool
    target_issue_progress: Literal["improved", "unchanged", "worse", "uncertain"]
    regression_flags: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    rationale: str


class PairwiseComparison(StrictModel):
    baseline_version_id: str
    candidate_version_id: str
    verdict: Literal["candidate_preferred", "baseline_preferred", "uncertain"]
    target_issue_progress: Literal["improved", "unchanged", "worse", "uncertain"]
    changed_sections: list[str] = Field(default_factory=list)
    regression_flags: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    votes: list[NormalizedVote] = Field(default_factory=list)
    failed_calls: int = Field(default=0, ge=0, le=2)
    reason: str

    @property
    def candidate_preferred(self) -> bool:
        return self.verdict == "candidate_preferred"


def _prompt(prompt_root: Path | None) -> PromptSpec:
    path = (prompt_root or default_prompt_root()) / "optimization_compare_prompt.v1.0.md"
    content = path.read_text(encoding="utf-8").strip()
    if len(content) < 500:
        raise ValueError(f"comparison prompt is unexpectedly short: {path}")
    return PromptSpec(
        prompt_id="optimization_compare_prompt",
        version="1.0",
        path=path,
        content=content,
        sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def _changed_fields(baseline: LessonPlanVersion, candidate: LessonPlanVersion) -> list[str]:
    old = baseline.document.model_dump(mode="json")
    new = candidate.document.model_dump(mode="json")
    return [field for field in _CONTENT_FIELDS if old[field] != new[field]]


def _shared_context(document: dict[str, object]) -> dict[str, object]:
    """Give pedagogical context without resending unchanged whole documents."""

    return {
        "metadata": document["metadata"],
        "design_thesis": document["design_thesis"],
        "learning_objectives": document["learning_objectives"],
        "procedure_stage_names": [
            step.get("stage", "") for step in document["procedure_steps"]
        ],
        "assessment_plan": document["assessment_plan"],
    }


def _payload(
    task: LessonTask,
    baseline: LessonPlanVersion,
    candidate: LessonPlanVersion,
    changed: list[str],
    *,
    candidate_first: bool,
) -> dict[str, object]:
    old = baseline.document.model_dump(mode="json")
    new = candidate.document.model_dump(mode="json")
    first, second = (new, old) if candidate_first else (old, new)
    return {
        "task": {
            "subject": task.subject,
            "grade": task.grade,
            "topic": task.topic,
            "duration_minutes": task.duration_minutes,
            "curriculum_standards": task.curriculum_standards,
            "learning_objectives": task.learning_objectives,
            "student_profile": task.student_profile,
            "class_constraints": task.class_constraints,
            "available_resources": task.available_resources,
        },
        "focus_sections": changed,
        "A": {
            "context": _shared_context(first),
            "focus_content": {field: first[field] for field in changed},
        },
        "B": {
            "context": _shared_context(second),
            "focus_content": {field: second[field] for field in changed},
        },
        "evidence_limit": "Only the displayed content is available. Do not infer missing critique text or classroom outcomes.",
    }


def _normalize(vote: PairwiseVote, *, candidate_first: bool) -> NormalizedVote:
    if vote.preferred in {"tie", "uncertain"}:
        preference = "uncertain"
    elif (vote.preferred == "A") == candidate_first:
        preference = "candidate"
    else:
        preference = "baseline"
    # The model reports A's focus progress relative to B. Convert it into
    # candidate-relative progress before combining the swapped assessments.
    progress = vote.target_issue_progress
    if not candidate_first:
        progress = {"improved": "worse", "worse": "improved"}.get(progress, progress)
    return NormalizedVote(
        order="candidate_first" if candidate_first else "baseline_first",
        preference=preference,
        substantive_progress=vote.substantive_progress,
        target_issue_progress=progress,
        regression_flags=vote.regression_flags,
        evidence=vote.evidence,
        rationale=vote.rationale,
    )


def _distinct(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _comparison(
    baseline: LessonPlanVersion,
    candidate: LessonPlanVersion,
    changed: list[str],
    votes: list[NormalizedVote],
    failed_calls: int,
    *,
    override_reason: str = "",
) -> PairwiseComparison:
    regressions = _distinct([flag for vote in votes for flag in vote.regression_flags])
    evidence = _distinct([item for vote in votes for item in vote.evidence])[:6]
    progress = (
        votes[0].target_issue_progress
        if len(votes) == 2
        and votes[0].target_issue_progress == votes[1].target_issue_progress
        else "uncertain"
    )
    if override_reason:
        verdict, reason = "uncertain", override_reason
    elif failed_calls:
        verdict, reason = "uncertain", "At least one blinded assessment failed; no quality preference is certified."
    elif len(votes) != 2:
        verdict, reason = "uncertain", "Both order-balanced assessments are required."
    elif all(v.preference == "candidate" for v in votes):
        if all(v.substantive_progress for v in votes) and progress == "improved" and not regressions:
            verdict = "candidate_preferred"
            reason = "Both assessment orders favor a substantive improvement without a reported regression."
        else:
            verdict = "uncertain"
            reason = "Candidate preference lacks consistent substantive progress or has regression concerns."
    elif all(v.preference == "baseline" for v in votes):
        verdict, reason = "baseline_preferred", "Both assessment orders favor the baseline."
    else:
        verdict, reason = "uncertain", "Order-balanced assessments disagree or are inconclusive."
    return PairwiseComparison(
        baseline_version_id=baseline.version_id,
        candidate_version_id=candidate.version_id,
        verdict=verdict,
        target_issue_progress=progress,
        changed_sections=changed,
        regression_flags=regressions,
        evidence=evidence,
        votes=votes,
        failed_calls=failed_calls,
        reason=reason,
    )


def compare(
    provider: OpenAICompatibleProvider,
    task: LessonTask,
    baseline: LessonPlanVersion,
    candidate: LessonPlanVersion,
    *,
    prompt_root: Path | None = None,
) -> AgentOutput[PairwiseComparison]:
    """Assess a changed candidate, never equating Judge score drift with progress.

    One failed side makes the verdict uncertain. Provider failures contribute
    their available usage and cost; the full documents are never in the result.
    """

    if baseline.document.task_id != task.task_id or candidate.document.task_id != task.task_id:
        raise ValueError("comparison versions must belong to the same task")
    if baseline.document.plan_id != candidate.document.plan_id:
        raise ValueError("comparison versions must share the same plan identity")
    changed = _changed_fields(baseline, candidate)
    if baseline.document.metadata != candidate.document.metadata:
        return AgentOutput(value=_comparison(
            baseline, candidate, changed, [], 0,
            override_reason="Lesson identity or duration changed; the candidate cannot be certified by content comparison.",
        ))
    if not candidate.rule_check_report.passed:
        return AgentOutput(value=_comparison(
            baseline, candidate, changed, [], 0,
            override_reason="Candidate fails deterministic lesson-plan rules; independent human review is required.",
        ))
    if not changed:
        return AgentOutput(value=_comparison(
            baseline, candidate, [], [], 0,
            override_reason="No canonical lesson-plan content changed; a score difference is not an optimization.",
        ))
    prompt = _prompt(prompt_root)
    first_payload = _payload(task, baseline, candidate, changed, candidate_first=False)
    second_payload = _payload(task, baseline, candidate, changed, candidate_first=True)
    if max(len(json.dumps(payload, ensure_ascii=False)) for payload in (first_payload, second_payload)) > _MAX_PAYLOAD_CHARACTERS:
        return AgentOutput(value=_comparison(
            baseline, candidate, changed, [], 0,
            override_reason="Changed content exceeds the bounded comparison input; human review is required.",
        ))

    total_input = total_output = 0
    total_cost = 0.0
    attempts = failed_calls = 0
    metadata: AgentCallMetadata | None = None
    response_ids: list[str] = []
    votes: list[NormalizedVote] = []
    for candidate_first, payload in ((False, first_payload), (True, second_payload)):
        try:
            response = provider.invoke_structured(
                prompt=prompt,
                input_payload=payload,
                output_schema=PairwiseVote,
                stage="optimization_pairwise_compare",
                max_attempts=1,
                max_output_tokens=2048,
            )
            votes.append(_normalize(response.value, candidate_first=candidate_first))
            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens
            total_cost += response.estimated_cost
            attempts += response.metadata.attempts
            metadata = response.metadata
            if response.metadata.response_id:
                response_ids.append(response.metadata.response_id)
        except ProviderInvocationError as error:
            failed_calls += 1
            attempts += error.attempts
            total_input += error.usage.input_tokens
            total_output += error.usage.output_tokens
            total_cost += error.estimated_cost
        except Exception:
            # Do not leak provider exception text (it can contain credentials or
            # lesson contents). Unknown failures have no trusted usage record.
            failed_calls += 1
            attempts += 1

    if attempts:
        metadata = AgentCallMetadata(
            provider=metadata.provider if metadata else getattr(getattr(provider, "settings", None), "provider", "unknown"),
            model_name=metadata.model_name if metadata else getattr(getattr(provider, "settings", None), "model_name", "unknown"),
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            prompt_sha256=prompt.sha256,
            response_id="|".join(response_ids),
            finish_reason="pairwise_complete" if not failed_calls else "pairwise_partial_failure",
            attempts=attempts,
            thinking_mode=metadata.thinking_mode if metadata else "unknown",
        )
    return AgentOutput(
        value=_comparison(baseline, candidate, changed, votes, failed_calls),
        usage=TokenUsage(input_tokens=total_input, output_tokens=total_output),
        estimated_cost=total_cost,
        metadata=metadata,
    )
