from app.llm.mock import MockProvider
from app.web.service import ClassroomService
from tests.f3_helpers import one_material_request, wait_until


def test_event_ids_sequences_timestamps_and_material_are_stable(tmp_path):
    service = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: MockProvider(),
    )
    snapshot, _ = service.create_session(one_material_request("events"))
    sid = snapshot["sessionId"]
    wait_until(lambda: service.get_session(sid)["status"] == "COMPLETED", timeout=3)
    events = service.get_events(sid)

    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    assert len({e["eventId"] for e in events}) == len(events)
    for event in events:
        assert event["occurredAt"].endswith("Z")
        assert event["completedAt"].endswith("Z")
        assert event["wallClockDurationMs"] >= 0
        assert event["estimatedTeachingSeconds"] is None
        assert event["estimated"] is False
        assert event["trigger"]["type"] in {"INITIALIZATION", "TIMEOUT", "USER_INPUT", "EMPTY_ENTER"}
    teach = next(e for e in events if e["function"] == "teach")
    assert teach["material"]["materialId"] == "m1"
    assert teach["material"]["sourceSectionId"] == "section-new-knowledge"
