from app.analysis.evidence_validator import EvidenceValidator
from app.contracts.event import ClassroomEventRecord


def make_event(event_id, seq, speaker, content):
    return ClassroomEventRecord.model_validate(
        {
            "eventId": event_id,
            "sequence": seq,
            "sessionId": "s1",
            "occurredAt": "2026-10-05T00:00:00.000Z",
            "completedAt": "2026-10-05T00:00:00.010Z",
            "wallClockDurationMs": 10,
            "estimatedTeachingSeconds": None,
            "estimated": False,
            "trigger": {"type": "TIMEOUT", "content": None},
            "managerDecision": {
                "speaker": speaker,
                "function": "ask_question",
                "reason": "test",
                "endClass": False,
            },
            "speaker": speaker,
            "roleLabel": speaker,
            "function": "ask_question",
            "content": content,
            "material": {
                "materialId": "m1",
                "title": "新知探究",
                "sourceSectionId": "sec1",
            },
            "status": "COMPLETED",
            "error": None,
        }
    )


def base_issue():
    return {
        "nativeIssueId": "ISSUE-01",
        "category": "interaction_gap",
        "severity": "MEDIUM",
        "title": "问题",
        "problem": "测试问题",
        "evidence": [
            {
                "eventId": "e1",
                "sequence": 1,
                "speaker": "inquisitive_mind",
                "contentQuote": "k 可以等于 0 吗",
            }
        ],
        "resolvedInSimulation": True,
        "resolutionEvidenceEventIds": ["e2"],
        "resolution": "后续回应",
        "suggestedAction": "加入边界辨析",
        "targetLessonSection": "新知探究",
        "confidence": 0.8,
    }


def test_valid_evidence_passes():
    events = [
        make_event("e1", 1, "inquisitive_mind", "k 可以等于 0 吗？"),
        make_event("e2", 2, "teacher", "不能，一次函数要求 k 不等于 0。"),
    ]
    outcome = EvidenceValidator().validate(
        [base_issue()], events, [{"materialId": "m1", "title": "新知探究"}]
    )
    assert len(outcome.valid_issues) == 1
    assert outcome.warnings == []


def test_wrong_event_quote_and_reverse_resolution_are_rejected():
    events = [
        make_event("e1", 1, "inquisitive_mind", "k 可以等于 0 吗？"),
        make_event("e2", 2, "teacher", "解释"),
    ]
    issue = base_issue()
    issue["evidence"][0]["contentQuote"] = "日志里不存在的句子"
    issue["resolutionEvidenceEventIds"] = ["e1"]
    outcome = EvidenceValidator().validate(
        [issue], events, [{"materialId": "m1", "title": "新知探究"}]
    )
    assert outcome.valid_issues == []
    assert any("contentQuote not found" in w for w in outcome.warnings)
    assert any("resolution evidence must occur after" in w for w in outcome.warnings)
