import json

import pytest

from app.contracts.session import CreateSessionRequest
from app.llm.mock import MockProvider
from app.teaching_plan import parse_teaching_script
from app.web.service import ClassroomService


def _sample_script():
    return """## 教学过程

| 环节与教师活动 | 学生任务与产出 | 评价与调控 |
|---|---|---|
| **一、复习导入（5分钟）**；教师复习旧知。 | 学生口答。 | 观察回答。 |
| **二、探究新知（12分钟）**；教师组织操作探究。 | 学生操作并交流。 | 检查关键步骤。 |
| **三、课堂小结（3分钟）**；教师组织总结。 | 学生说收获。 |  |
"""


def _request(key="plan-1", roles=None):
    body = {
        "lessonId": "L1",
        "versionId": "V1",
        "modelMode": "MOCK",
        "requestKey": key,
        "timeoutSeconds": 30,
        "maxConsecutiveTimeouts": 10,
        "maxEvents": 30,
        "maxWallClockSeconds": 60,
        "materials": [{
            "materialId": "1",
            "title": "教学过程",
            "teachingScript": _sample_script(),
            "keyPoints": [],
            "sourceSectionId": "sec-teaching-process",
            "metadata": {"source_section_type": "teaching_process"},
        }],
    }
    if roles is not None:
        body["activeRoles"] = roles
    return CreateSessionRequest.model_validate(body)


def test_parser_splits_teaching_process_rows():
    sections = parse_teaching_script(_sample_script())
    assert [s.title for s in sections] == ["一、复习导入", "二、探究新知", "三、课堂小结"]
    assert [s.duration_minutes for s in sections] == [5, 12, 3]
    assert sections[1].student_task == "学生操作并交流。"


def test_formal_service_auto_splits_single_teaching_process_material(tmp_path):
    service = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: MockProvider(),
        auto_start=False,
    )
    snapshot, replay = service.create_session(_request())
    assert replay is False
    assert snapshot["inputMode"] == "TEACHING_PROCESS_SPLIT"
    assert len(snapshot["inputMaterials"]) == 1
    assert len(snapshot["materials"]) == 3
    assert snapshot["materials"][0]["title"] == "一、复习导入"
    assert snapshot["materials"][0]["durationMinutes"] == 5
    assert snapshot["materials"][0]["sourceSectionId"] == "sec-teaching-process"
    assert snapshot["materials"][0]["metadata"]["splitFromTeachingProcess"] is True


def test_existing_single_plain_material_remains_direct(tmp_path):
    service = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: MockProvider(),
        auto_start=False,
    )
    body = _request("direct").model_dump(by_alias=True)
    body["materials"][0]["title"] = "一次函数定义"
    body["materials"][0]["teachingScript"] = "一次函数一般形式是 y=kx+b。"
    req = CreateSessionRequest.model_validate(body)
    snapshot, _ = service.create_session(req)
    assert snapshot["inputMode"] == "DIRECT"
    assert len(snapshot["materials"]) == 1


def test_active_roles_are_enforced_and_exposed(tmp_path):
    service = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: MockProvider(),
        auto_start=False,
    )
    snapshot, _ = service.create_session(_request("roles", ["teacher", "note_taker"]))
    assert snapshot["activeRoles"] == ["teacher", "note_taker"]
    runtime = service._sessions[snapshot["sessionId"]]
    assert runtime.classroom.state.active_roles == ["teacher", "note_taker"]


def test_active_roles_must_include_teacher():
    with pytest.raises(Exception):
        _request("bad-role", ["assistant"])
