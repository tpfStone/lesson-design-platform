from app.analysis.issue_agent import IssueAnalysisAgent
from app.contracts.event import ClassroomEventRecord
from app.llm.mock import MockProvider


def test_mock_issue_agent_only_emits_evidence_backed_issue():
    event = ClassroomEventRecord.model_validate(
        {
            "eventId": "e-ask",
            "sequence": 1,
            "sessionId": "s1",
            "occurredAt": "2026-10-05T00:00:00.000Z",
            "completedAt": "2026-10-05T00:00:00.010Z",
            "wallClockDurationMs": 10,
            "estimatedTeachingSeconds": None,
            "estimated": False,
            "trigger": {"type": "TIMEOUT", "content": None},
            "managerDecision": {
                "speaker": "inquisitive_mind",
                "function": "ask_question",
                "reason": "促进思考",
                "endClass": False,
            },
            "speaker": "inquisitive_mind",
            "roleLabel": "好奇提问者",
            "function": "ask_question",
            "content": "k 等于 0 时是否还是一次函数？",
            "material": {
                "materialId": "m1",
                "title": "新知探究",
                "sourceSectionId": "sec1",
            },
            "status": "COMPLETED",
            "error": None,
        }
    )
    result = IssueAnalysisAgent(MockProvider()).analyze(
        session_id="s1",
        version_id="v1",
        events=[event],
        materials=[{"materialId": "m1", "title": "新知探究", "sourceSectionId": "sec1"}],
        session_status="COMPLETED",
        stop_reason="MANAGER_END_CLASS",
    )
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.evidence[0].event_id == "e-ask"
    assert issue.evidence[0].content_quote in event.content
    assert issue.target_lesson_section == "m1"
    assert result.action_items[0]["sourceIssueId"] == issue.native_issue_id


def _event(seq: int, content: str = "课堂事件", material_id: str = "m1"):
    return ClassroomEventRecord.model_validate(
        {
            "eventId": f"e-{seq}",
            "sequence": seq,
            "sessionId": "s-long",
            "occurredAt": "2026-10-05T00:00:00.000Z",
            "completedAt": "2026-10-05T00:00:00.010Z",
            "wallClockDurationMs": 10,
            "estimatedTeachingSeconds": None,
            "estimated": False,
            "trigger": {"type": "TIMEOUT", "content": None},
            "managerDecision": {
                "speaker": "teacher",
                "function": "discuss",
                "reason": "test",
                "endClass": False,
            },
            "speaker": "teacher",
            "roleLabel": "教师",
            "function": "discuss",
            "content": content,
            "material": {
                "materialId": material_id,
                "title": "章节A",
                "sourceSectionId": "secA",
            },
            "status": "COMPLETED",
            "error": None,
        }
    )


def test_real_agent_long_session_is_chunked_before_analysis():
    class CountingLLM:
        name = "fake-real"
        def __init__(self):
            self.calls = 0
        def chat(self, messages, temperature=0.1):
            self.calls += 1
            return '{"issues": []}'

    llm = CountingLLM()
    events = [_event(i) for i in range(1, 26)]
    result = IssueAnalysisAgent(llm).analyze(
        session_id="s-long",
        version_id="v-long",
        events=events,
        materials=[{"materialId": "m1", "title": "章节A", "sourceSectionId": "secA"}],
        session_status="COMPLETED",
        stop_reason="MANAGER_END_CLASS",
        model_mode="REAL",
    )
    assert llm.calls == 2  # 20 + 5 event windows
    assert result.issues == []
    assert result.model_mode == "REAL"


def test_real_agent_retries_invalid_evidence_once_then_accepts_repair():
    import json

    class RepairLLM:
        name = "fake-real"
        def __init__(self):
            self.calls = 0
        def chat(self, messages, temperature=0.1):
            self.calls += 1
            quote = "不存在的引文" if self.calls == 1 else "真实课堂原文"
            return json.dumps({
                "issues": [{
                    "nativeIssueId": "ISSUE-01",
                    "category": "interaction_gap",
                    "severity": "MEDIUM",
                    "title": "测试问题",
                    "problem": "测试",
                    "evidence": [{
                        "eventId": "e-1",
                        "sequence": 1,
                        "speaker": "teacher",
                        "contentQuote": quote
                    }],
                    "resolvedInSimulation": False,
                    "resolutionEvidenceEventIds": [],
                    "resolution": None,
                    "suggestedAction": "补充回应",
                    "targetLessonSection": "章节A",
                    "confidence": 0.8
                }]
            }, ensure_ascii=False)

    llm = RepairLLM()
    result = IssueAnalysisAgent(llm).analyze(
        session_id="s1",
        version_id="v1",
        events=[_event(1, content="真实课堂原文")],
        materials=[{"materialId": "m1", "title": "章节A", "sourceSectionId": "secA"}],
        session_status="COMPLETED",
        stop_reason="MANAGER_END_CLASS",
        model_mode="REAL",
    )
    assert llm.calls == 2
    assert len(result.issues) == 1
    assert result.issues[0].evidence[0].content_quote == "真实课堂原文"
    assert any("contentQuote not found" in warning for warning in result.warnings)


def test_real_agent_consolidates_similar_validated_issues_before_action_items():
    import json

    class DuplicateRootLLM:
        name = "fake-real"

        def chat(self, messages, temperature=0.1):
            return json.dumps(
                {
                    "issues": [
                        {
                            "nativeIssueId": "ISSUE-A",
                            "category": "interaction_gap",
                            "severity": "MEDIUM",
                            "title": "提问后没有等待学生回答",
                            "problem": "教师提问后直接继续。",
                            "evidence": [
                                {
                                    "eventId": "e-1",
                                    "sequence": 1,
                                    "speaker": "teacher",
                                    "contentQuote": "真实课堂原文",
                                }
                            ],
                            "resolvedInSimulation": False,
                            "resolutionEvidenceEventIds": [],
                            "resolution": None,
                            "suggestedAction": "留出等待时间",
                            "targetLessonSection": "章节A",
                            "confidence": 0.8,
                        },
                        {
                            "nativeIssueId": "ISSUE-B",
                            "category": "assessment_gap",
                            "severity": "HIGH",
                            "title": "检查题未采集学生答案",
                            "problem": "教师直接公布答案。",
                            "evidence": [
                                {
                                    "eventId": "e-1",
                                    "sequence": 1,
                                    "speaker": "teacher",
                                    "contentQuote": "真实课堂原文",
                                }
                            ],
                            "resolvedInSimulation": False,
                            "resolutionEvidenceEventIds": [],
                            "resolution": None,
                            "suggestedAction": "先让学生回答再反馈",
                            "targetLessonSection": "m1",
                            "confidence": 0.9,
                        },
                    ]
                },
                ensure_ascii=False,
            )

    result = IssueAnalysisAgent(DuplicateRootLLM()).analyze(
        session_id="s1",
        version_id="v1",
        events=[_event(1, content="真实课堂原文")],
        materials=[{"materialId": "m1", "title": "章节A", "sourceSectionId": "secA"}],
        session_status="COMPLETED",
        stop_reason="MANAGER_END_CLASS",
        model_mode="REAL",
    )

    assert len(result.issues) == 1
    assert len(result.action_items) == 1
    assert result.issues[0].severity == "HIGH"
    assert result.issues[0].target_lesson_section == "m1"
    assert "缺少学生作答—反馈闭环" in result.issues[0].title
    assert result.action_items[0]["sourceIssueId"] == result.issues[0].native_issue_id
    assert any("merged candidates" in warning for warning in result.warnings)
