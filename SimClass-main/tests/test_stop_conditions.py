from datetime import datetime, timedelta, timezone

from app.llm.mock import MockProvider
from app.web.service import ClassroomService
from tests.f3_helpers import one_material_request, wait_until


def test_max_events_interrupts_with_explicit_reason(tmp_path):
    service = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: MockProvider(),
    )
    req = one_material_request("limit-events", max_events=2, max_timeouts=100)
    snapshot, _ = service.create_session(req)
    sid = snapshot["sessionId"]
    final = wait_until(
        lambda: (
            s if (s := service.get_session(sid))["status"] == "INTERRUPTED" else None
        ),
        timeout=2,
    )
    assert final["stopReason"] == "MAX_EVENTS"
    assert len(service.get_events(sid)) == 2


def test_expired_wall_clock_interrupts(tmp_path):
    service = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: MockProvider(),
        auto_start=False,
    )
    snapshot, _ = service.create_session(one_material_request("limit-time", timeout=30, max_wall=1))
    sid = snapshot["sessionId"]
    runtime = service._sessions[sid]
    runtime.started_at = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat().replace("+00:00", "Z")
    service.start_session(sid)
    final = wait_until(
        lambda: (
            s if (s := service.get_session(sid))["status"] == "INTERRUPTED" else None
        ),
        timeout=2,
    )
    assert final["stopReason"] == "MAX_WALL_CLOCK_SECONDS"


def test_manual_pause_resume_and_end_are_real_states(tmp_path):
    service = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: MockProvider(),
    )
    snapshot, _ = service.create_session(one_material_request("controls", timeout=30))
    sid = snapshot["sessionId"]
    wait_until(lambda: len(service.get_events(sid)) == 1)
    paused = service.pause(sid)
    assert paused["status"] == "PAUSED"
    assert paused["pauseReason"] == "MANUAL"

    service.send_message(sid, "暂停期间先排队的问题？")
    assert len(service.get_events(sid)) == 1
    resumed = service.resume(sid)
    assert resumed["status"] == "RUNNING"
    wait_until(lambda: len(service.get_events(sid)) >= 2)
    stopping = service.end(sid)
    assert stopping["status"] in {"STOPPING", "INTERRUPTED"}
    final = wait_until(
        lambda: (
            s if (s := service.get_session(sid))["status"] == "INTERRUPTED" else None
        ),
        timeout=2,
    )
    assert final["stopReason"] == "MANUAL_END"


def test_material_completion_is_independent_stop_condition(tmp_path):
    import json
    from app.llm.mock import MockProvider

    class NoEndMock(MockProvider):
        def _manager_reply(self, context: str) -> str:
            if "所有材料已完成: yes" in context:
                return json.dumps(
                    {
                        "speaker": "teacher",
                        "function": "summarize",
                        "reason": "总结但故意不 end_class，用于验证材料完成兜底",
                        "end_class": False,
                    },
                    ensure_ascii=False,
                )
            return super()._manager_reply(context)

    service = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: NoEndMock(),
    )
    snapshot, _ = service.create_session(one_material_request("material-stop", max_timeouts=100))
    sid = snapshot["sessionId"]
    final = wait_until(
        lambda: (
            s if (s := service.get_session(sid))["status"] == "COMPLETED" else None
        ),
        timeout=2,
    )
    assert final["stopReason"] == "MATERIALS_COMPLETED"
    assert service._sessions[sid].classroom.state.all_materials_finished


def test_timeout_safety_pause_is_visible_and_resume_resets_cycle(tmp_path):
    service = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: MockProvider(),
    )
    snapshot, _ = service.create_session(
        one_material_request("timeout-pause", timeout=0.02, max_timeouts=1, max_events=20)
    )
    sid = snapshot["sessionId"]
    paused = wait_until(
        lambda: (
            s if (s := service.get_session(sid))["status"] == "PAUSED" else None
        ),
        timeout=2,
    )
    assert paused["pauseReason"] == "MAX_CONSECUTIVE_TIMEOUTS"
    assert service._sessions[sid].classroom.state.autonomous_mode is False

    service.resume(sid)
    wait_until(lambda: len(service.get_events(sid)) >= 3, timeout=2)
    runtime = service._sessions[sid]
    assert runtime.classroom.state.autonomous_mode is True
    # empty_enter resume event resets the counter before a new timeout cycle begins.
    assert any(e["trigger"]["type"] == "EMPTY_ENTER" for e in service.get_events(sid))
    service.end(sid)
