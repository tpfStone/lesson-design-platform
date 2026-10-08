from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.contracts.analysis import EvidenceRef, IssueRecord


_SEVERITY_RANK = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}

# These three categories often describe the same root implementation failure:
# a teacher prompt/activity did not become an observable student-response-feedback loop.
_ENGAGEMENT_FEEDBACK_CATEGORIES = {
    "interaction_gap",
    "assessment_gap",
    "participation_imbalance",
}

_CATEGORY_PRIORITY = {
    "assessment_gap": 3,
    "interaction_gap": 2,
    "participation_imbalance": 1,
}


@dataclass
class ConsolidationOutcome:
    issues: list[IssueRecord]
    warnings: list[str]


@dataclass
class _GroupedIssue:
    issue: IssueRecord
    merged_from: list[str]


class IssueConsolidator:
    """Deterministic post-processor for evidence-validated F3 issues.

    Responsibilities:
    1. Normalize targetLessonSection to a stable materialId when possible.
    2. Merge repeated engagement/feedback failures inside the same lesson material.
    3. Rank by severity, confidence, recurrence and evidence strength.
    4. Keep only the highest-value issues for downstream consumers such as F4.

    This class does *not* invent new evidence. Merged issues only contain evidence
    that already survived EvidenceValidator.
    """

    def __init__(self, max_final_issues: int = 5, max_evidence_per_issue: int = 6):
        self.max_final_issues = max(1, int(max_final_issues))
        self.max_evidence_per_issue = max(1, int(max_evidence_per_issue))

    def consolidate(
        self,
        issues: list[IssueRecord],
        materials: list[dict[str, Any]],
    ) -> ConsolidationOutcome:
        if not issues:
            return ConsolidationOutcome(issues=[], warnings=[])

        token_to_material_id, material_title = self._material_maps(materials)
        groups: dict[tuple[str, str], list[IssueRecord]] = {}
        order: list[tuple[str, str]] = []

        for issue in issues:
            canonical_target = self._canonical_target(
                issue.target_lesson_section, token_to_material_id
            )
            family = self._family(issue)
            key = (canonical_target or "__unmapped__", family)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(issue)

        grouped: list[_GroupedIssue] = []
        warnings: list[str] = []
        for key in order:
            target, family = key
            members = groups[key]
            if family == "engagement_feedback" and len(members) > 1:
                merged = self._merge_engagement_feedback(
                    members,
                    canonical_target=None if target == "__unmapped__" else target,
                    material_title=material_title,
                )
                warnings.append(
                    "issue consolidation: merged candidates "
                    + ", ".join(issue.native_issue_id for issue in members)
                    + f" at target {target} into one engagement/feedback issue"
                )
                grouped.append(
                    _GroupedIssue(
                        issue=merged,
                        merged_from=[issue.native_issue_id for issue in members],
                    )
                )
            else:
                for member in members:
                    copied = member.model_copy(deep=True)
                    if target != "__unmapped__":
                        copied.target_lesson_section = target
                    grouped.append(
                        _GroupedIssue(issue=copied, merged_from=[member.native_issue_id])
                    )

        grouped.sort(key=self._rank_key, reverse=True)
        before_limit = len(grouped)
        grouped = grouped[: self.max_final_issues]
        if before_limit > self.max_final_issues:
            warnings.append(
                f"issue ranking: kept top {self.max_final_issues} of {before_limit} consolidated issues"
            )

        final: list[IssueRecord] = []
        for index, item in enumerate(grouped, start=1):
            item.issue.native_issue_id = f"ISSUE-{index:02d}"
            final.append(item.issue)

        return ConsolidationOutcome(issues=final, warnings=warnings)

    @staticmethod
    def _material_maps(
        materials: list[dict[str, Any]],
    ) -> tuple[dict[str, str], dict[str, str]]:
        token_to_material_id: dict[str, str] = {}
        material_title: dict[str, str] = {}
        for material in materials:
            material_id = str(
                material.get("materialId")
                or material.get("material_id")
                or material.get("id")
                or ""
            ).strip()
            if not material_id:
                continue
            title = str(material.get("title") or material_id).strip()
            material_title[material_id] = title
            for key in (
                "materialId",
                "material_id",
                "id",
                "title",
                "sourceSectionId",
                "source_section_id",
            ):
                value = material.get(key)
                if value is not None and str(value).strip():
                    token_to_material_id[str(value).strip()] = material_id
        return token_to_material_id, material_title

    @staticmethod
    def _canonical_target(
        target: str | None,
        token_to_material_id: dict[str, str],
    ) -> str | None:
        if target is None or not target.strip():
            return None
        stripped = target.strip()
        return token_to_material_id.get(stripped, stripped)

    @staticmethod
    def _family(issue: IssueRecord) -> str:
        if issue.category in _ENGAGEMENT_FEEDBACK_CATEGORIES:
            return "engagement_feedback"
        # Keep distinct misconception/explanation/transition/pace issues separate.
        # Their semantics can differ substantially even inside the same material.
        return f"{issue.category}:{issue.native_issue_id}"

    def _merge_engagement_feedback(
        self,
        members: list[IssueRecord],
        *,
        canonical_target: str | None,
        material_title: dict[str, str],
    ) -> IssueRecord:
        representative = max(members, key=self._representative_key)
        evidence = self._merge_evidence(members)
        section_label = (
            material_title.get(canonical_target, canonical_target)
            if canonical_target
            else "该教学环节"
        )
        observed_titles = self._unique([issue.title.strip() for issue in members])

        problem = (
            f"{section_label}中多次出现同一类实施问题：教师提出问题、练习或检查后，"
            "没有形成稳定的“学生作答—教师依据作答反馈/纠错”闭环。"
            "具体表现包括："
            + "；".join(observed_titles)
            + "。"
        )
        suggested_action = (
            "把该环节统一改造成“教师提问/布置任务 → 明确等待 → 学生独立或同伴作答 → "
            "抽样展示 → 教师依据真实回答反馈/纠错”的闭环；答案和完整讲解应延后到学生"
            "表态之后，并用点名、投票、同伴互说等方式扩大参与面。"
        )

        all_resolved = all(issue.resolved_in_simulation for issue in members)
        resolution_ids = self._unique(
            [
                event_id
                for issue in members
                for event_id in issue.resolution_evidence_event_ids
            ]
        )
        resolution = None
        if all_resolved:
            resolutions = self._unique(
                [issue.resolution.strip() for issue in members if issue.resolution]
            )
            resolution = "；".join(resolutions) or representative.resolution

        return IssueRecord(
            nativeIssueId=representative.native_issue_id,
            category=representative.category,
            severity=max(members, key=lambda item: _SEVERITY_RANK.get(item.severity, 0)).severity,
            title=f"{section_label}缺少学生作答—反馈闭环",
            problem=problem,
            evidence=evidence,
            resolvedInSimulation=all_resolved,
            resolutionEvidenceEventIds=resolution_ids if all_resolved else [],
            resolution=resolution,
            suggestedAction=suggested_action,
            targetLessonSection=canonical_target or representative.target_lesson_section,
            confidence=max(issue.confidence for issue in members),
        )

    def _merge_evidence(self, members: list[IssueRecord]) -> list[EvidenceRef]:
        seen: set[tuple[str, str]] = set()
        evidence: list[EvidenceRef] = []
        for issue in sorted(members, key=self._representative_key, reverse=True):
            for ref in issue.evidence:
                key = (ref.event_id, ref.content_quote)
                if key in seen:
                    continue
                seen.add(key)
                evidence.append(ref.model_copy(deep=True))
        evidence.sort(key=lambda ref: ref.sequence)
        return evidence[: self.max_evidence_per_issue]

    @staticmethod
    def _representative_key(issue: IssueRecord) -> tuple[int, float, int, int]:
        return (
            _SEVERITY_RANK.get(issue.severity, 0),
            issue.confidence,
            _CATEGORY_PRIORITY.get(issue.category, 0),
            len(issue.evidence),
        )

    @staticmethod
    def _rank_key(item: _GroupedIssue) -> tuple[int, float, int, int]:
        issue = item.issue
        return (
            _SEVERITY_RANK.get(issue.severity, 0),
            issue.confidence,
            len(item.merged_from),
            len(issue.evidence),
        )

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result
