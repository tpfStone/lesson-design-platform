from app.llm.mock import MockProvider
from app.web.service import ClassroomService
from tests.f3_helpers import one_material_request, wait_until


def test_session_runs_dynamic_classroom_and_writes_artifacts(tmp_path):
    service = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: MockProvider(),
    )
    snapshot, replay = service.create_session(one_material_request("service-1"))
    assert replay is False
    session_id = snapshot["sessionId"]

    final = wait_until(
        lambda: (
            s if (s := service.get_session(session_id))["status"] in {"COMPLETED", "INTERRUPTED", "FAILED"} else None
        ),
        timeout=3,
    )
    assert final["status"] == "COMPLETED"
    assert final["modelMode"] == "MOCK"
    assert final["stopReason"] == "MANAGER_END_CLASS"

    events = service.get_events(session_id)
    assert len(events) >= 3
    assert any(e["function"] == "teach" for e in events)
    assert any(e["function"] == "summarize" for e in events)

    result = service.get_result(session_id)
    assert result["schemaVersion"] == "2.0"
    assert result["session"]["lessonId"] == "lesson-1"
    assert result["statistics"]["estimatedTeachingSeconds"] is None
    assert (tmp_path / session_id / "session_record.json").exists()
    assert (tmp_path / session_id / "classroom_summary.md").exists()
    assert (tmp_path / session_id / "issue_analysis.json").exists()


def test_request_key_is_idempotent(tmp_path):
    service = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: MockProvider(),
        auto_start=False,
    )
    first, replay1 = service.create_session(one_material_request("same-key"))
    second, replay2 = service.create_session(one_material_request("same-key"))
    assert replay1 is False
    assert replay2 is True
    assert first["sessionId"] == second["sessionId"]


def test_explicit_real_mode_cannot_silently_fall_back_to_mock(tmp_path):
    import pytest
    from app.contracts.session import CreateSessionRequest

    service = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: MockProvider(),
        auto_start=False,
    )
    raw = one_material_request("real-must-be-real").model_dump(by_alias=True)
    raw["modelMode"] = "REAL"
    request = CreateSessionRequest.model_validate(raw)
    with pytest.raises(RuntimeError, match="resolved to MOCK"):
        service.create_session(request)


def test_service_restart_marks_unrecoverable_active_session_interrupted(tmp_path):
    service1 = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: MockProvider(),
        auto_start=False,
    )
    snapshot, _ = service1.create_session(one_material_request("restart-case"))
    sid = snapshot["sessionId"]
    assert service1.get_session(sid)["status"] == "READY"

    service2 = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: MockProvider(),
        auto_start=False,
    )
    recovered = service2.get_session(sid)
    assert recovered["status"] == "INTERRUPTED"
    assert recovered["stopReason"] == "SERVICE_RESTART_UNRECOVERABLE"
