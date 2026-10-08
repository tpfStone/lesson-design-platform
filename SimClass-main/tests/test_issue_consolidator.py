from app.analysis.issue_consolidator import IssueConsolidator
from app.contracts.analysis import IssueRecord


def _issue(
    issue_id: str,
    *,
    category: str,
    severity: str = "MEDIUM",
    confidence: float = 0.8,
    target: str = "m1",
    event_id: str | None = None,
    sequence: int = 1,
    title: str | None = None,
):
    event_id = event_id or f"e-{issue_id}"
    return IssueRecord.model_validate(
        {
            "nativeIssueId": issue_id,
            "category": category,
            "severity": severity,
            "title": title or f"{issue_id} title",
            "problem": f"{issue_id} problem",
            "evidence": [
                {
                    "eventId": event_id,
                    "sequence": sequence,
                    "speaker": "teacher",
                    "contentQuote": f"quote-{issue_id}",
                }
            ],
            "resolvedInSimulation": False,
            "resolutionEvidenceEventIds": [],
            "resolution": None,
            "suggestedAction": f"action-{issue_id}",
            "targetLessonSection": target,
            "confidence": confidence,
        }
    )


MATERIALS = [
    {"materialId": "m1", "title": "概念导入", "sourceSectionId": "sec-1"},
    {"materialId": "m2", "title": "定义辨析", "sourceSectionId": "sec-2"},
    {"materialId": "m3", "title": "课堂练习", "sourceSectionId": "sec-3"},
    {"materialId": "m4", "title": "课堂总结", "sourceSectionId": "sec-4"},
]


def test_engagement_feedback_issues_in_same_material_are_merged():
    issues = [
        _issue("ISSUE-01", category="interaction_gap", target="m2", event_id="e1", sequence=1),
        _issue("ISSUE-02", category="assessment_gap", target="定义辨析", event_id="e2", sequence=2),
        _issue("ISSUE-03", category="participation_imbalance", target="sec-2", event_id="e3", sequence=3),
    ]

    outcome = IssueConsolidator(max_final_issues=5).consolidate(issues, MATERIALS)

    assert len(outcome.issues) == 1
    merged = outcome.issues[0]
    assert merged.target_lesson_section == "m2"
    assert merged.title == "定义辨析缺少学生作答—反馈闭环"
    assert {ref.event_id for ref in merged.evidence} == {"e1", "e2", "e3"}
    assert "学生作答—教师依据作答反馈/纠错" in merged.problem
    assert any("merged candidates" in warning for warning in outcome.warnings)


def test_distinct_explanation_issue_is_not_merged_into_engagement_gap():
    issues = [
        _issue("ISSUE-01", category="interaction_gap", target="m3"),
        _issue("ISSUE-02", category="assessment_gap", target="m3", sequence=2),
        _issue(
            "ISSUE-03",
            category="insufficient_explanation",
            target="m3",
            sequence=3,
            title="定义解释不足",
        ),
    ]

    outcome = IssueConsolidator(max_final_issues=5).consolidate(issues, MATERIALS)

    assert len(outcome.issues) == 2
    categories = {issue.category for issue in outcome.issues}
    assert "insufficient_explanation" in categories
    assert len(categories & {"interaction_gap", "assessment_gap", "participation_imbalance"}) == 1


def test_ranking_keeps_top_five_by_severity_then_confidence():
    issues = [
        _issue("ISSUE-01", category="material_transition", severity="LOW", confidence=0.95, target="m1"),
        _issue("ISSUE-02", category="insufficient_explanation", severity="MEDIUM", confidence=0.6, target="m1"),
        _issue("ISSUE-03", category="student_misconception", severity="MEDIUM", confidence=0.7, target="m2"),
        _issue("ISSUE-04", category="pace_risk", severity="MEDIUM", confidence=0.8, target="m2"),
        _issue("ISSUE-05", category="other", severity="HIGH", confidence=0.6, target="m3"),
        _issue("ISSUE-06", category="insufficient_explanation", severity="HIGH", confidence=0.9, target="m4"),
    ]

    outcome = IssueConsolidator(max_final_issues=5).consolidate(issues, MATERIALS)

    assert len(outcome.issues) == 5
    assert all(issue.severity != "LOW" for issue in outcome.issues)
    assert outcome.issues[0].severity == "HIGH"
    assert outcome.issues[0].confidence == 0.9
    assert [issue.native_issue_id for issue in outcome.issues] == [
        "ISSUE-01",
        "ISSUE-02",
        "ISSUE-03",
        "ISSUE-04",
        "ISSUE-05",
    ]
    assert any("kept top 5" in warning for warning in outcome.warnings)
