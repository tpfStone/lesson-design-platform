from app.analysis.report_builder import render_summary_markdown


def test_summary_markdown_prefers_process_report_style():
    result = {
        "session": {
            "sessionId": "s-1",
            "lessonId": "l-1",
            "versionId": "v-1",
            "modelMode": "REAL",
            "modelProvider": "openai-compatible",
            "modelName": "deepseek-flash",
            "status": "COMPLETED",
            "stopReason": "MANAGER_END_CLASS",
            "startedAt": "2026-10-05T01:00:00Z",
            "finishedAt": "2026-10-05T01:01:00Z",
            "materials": [
                {
                    "materialId": "m1",
                    "title": "一次函数定义",
                    "sourceSectionId": "sec-1",
                }
            ],
        },
        "events": [
            {
                "eventId": "e1",
                "sequence": 1,
                "sessionId": "s-1",
                "occurredAt": "2026-10-05T01:00:00Z",
                "completedAt": "2026-10-05T01:00:02Z",
                "wallClockDurationMs": 2000,
                "estimatedTeachingSeconds": None,
                "estimated": False,
                "trigger": {"type": "INITIALIZATION", "content": None},
                "managerDecision": {
                    "speaker": "teacher",
                    "function": "teach",
                    "reason": "开始讲授当前材料",
                    "endClass": False,
                },
                "speaker": "teacher",
                "roleLabel": "教师",
                "function": "teach",
                "content": "同学们，今天学习一次函数。",
                "material": {
                    "materialId": "m1",
                    "title": "一次函数定义",
                    "sourceSectionId": "sec-1",
                },
                "status": "COMPLETED",
                "error": None,
            }
        ],
        "statistics": {
            "eventCount": 1,
            "roleCounts": {"teacher": 1},
            "functionCounts": {"teach": 1},
            "materialCoverage": [
                {"materialId": "m1", "title": "一次函数定义", "covered": True}
            ],
            "observedWallClockSeconds": 2.0,
            "estimatedTeachingSeconds": None,
        },
        "summary": {
            "rolesObserved": ["teacher"],
            "materialsCovered": ["一次函数定义"],
        },
    }

    text = render_summary_markdown(result)
    assert "## 课堂材料" in text
    assert "## 各轮记录" in text
    assert "### 第 1 轮" in text
    assert "课堂启动，开始当前教学材料" in text
    assert "发言角色：教师 (`teacher`)" in text
    assert "Manager 决策：`teacher / teach`" in text
    assert "同学们，今天学习一次函数。" in text
    assert "## 课堂统计" in text
    assert "## REAL / MOCK 边界" in text
    assert "deepseek-flash" in text
