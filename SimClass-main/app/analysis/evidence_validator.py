from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.contracts.analysis import ISSUE_CATEGORIES, SEVERITIES, IssueRecord
from app.contracts.event import ClassroomEventRecord


@dataclass
class ValidationOutcome:
    valid_issues: list[IssueRecord]
    warnings: list[str]


class EvidenceValidator:
    """Deterministic gatekeeper for IssueAnalysisAgent output.

    It never invents replacement evidence. Invalid issues are rejected so the
    caller can retry the model once; after that they stay rejected.
    """

    def __init__(self, max_issues: int = 12):
        self.max_issues = max_issues

    def validate(
        self,
        raw_issues: list[dict[str, Any]],
        events: list[ClassroomEventRecord],
        materials: list[dict[str, Any]],
    ) -> ValidationOutcome:
        event_by_id = {event.event_id: event for event in events}
        section_tokens = self._section_tokens(materials)
        valid: list[IssueRecord] = []
        warnings: list[str] = []

        if len(raw_issues) > self.max_issues:
            warnings.append(
                f"issue count {len(raw_issues)} exceeds max {self.max_issues}; extra issues rejected"
            )

        for index, raw in enumerate(raw_issues[: self.max_issues], start=1):
            issue_label = str(raw.get("nativeIssueId") or raw.get("native_issue_id") or f"#{index}")
            errors: list[str] = []
            try:
                issue = IssueRecord.model_validate(raw)
            except Exception as exc:
                warnings.append(f"{issue_label}: schema invalid: {exc}")
                continue

            if issue.category not in ISSUE_CATEGORIES:
                errors.append(f"category not allowed: {issue.category}")
            if issue.severity not in SEVERITIES:
                errors.append(f"severity not allowed: {issue.severity}")
            if not issue.evidence:
                errors.append("at least one evidence item is required")

            evidence_sequences: list[int] = []
            for ref in issue.evidence:
                event = event_by_id.get(ref.event_id)
                if event is None:
                    errors.append(f"evidence eventId not found: {ref.event_id}")
                    continue
                evidence_sequences.append(event.sequence)
                if ref.sequence != event.sequence:
                    errors.append(
                        f"evidence sequence mismatch for {ref.event_id}: {ref.sequence} != {event.sequence}"
                    )
                if ref.speaker != event.speaker:
                    errors.append(
                        f"evidence speaker mismatch for {ref.event_id}: {ref.speaker} != {event.speaker}"
                    )
                quote = ref.content_quote.strip()
                if not quote or quote not in (event.content or ""):
                    errors.append(f"contentQuote not found in event body: {ref.event_id}")

            latest_problem_sequence = max(evidence_sequences, default=0)
            for resolution_id in issue.resolution_evidence_event_ids:
                event = event_by_id.get(resolution_id)
                if event is None:
                    errors.append(f"resolution eventId not found: {resolution_id}")
                elif event.sequence <= latest_problem_sequence:
                    errors.append(
                        f"resolution evidence must occur after problem evidence: {resolution_id}"
                    )

            if issue.resolved_in_simulation and not issue.resolution_evidence_event_ids:
                errors.append("resolvedInSimulation=true requires resolutionEvidenceEventIds")

            if issue.target_lesson_section:
                target = issue.target_lesson_section.strip()
                if target not in section_tokens:
                    errors.append(f"targetLessonSection cannot be mapped: {target}")

            if errors:
                warnings.append(f"{issue_label}: rejected: " + "; ".join(errors))
            else:
                valid.append(issue)

        return ValidationOutcome(valid_issues=valid, warnings=warnings)

    @staticmethod
    def _section_tokens(materials: list[dict[str, Any]]) -> set[str]:
        tokens: set[str] = set()
        for material in materials:
            for key in ("title", "materialId", "material_id", "id", "sourceSectionId", "source_section_id"):
                value = material.get(key)
                if value is not None and str(value).strip():
                    tokens.add(str(value).strip())
        return tokens
