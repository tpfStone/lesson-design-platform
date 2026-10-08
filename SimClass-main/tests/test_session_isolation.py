import time

from app.llm.mock import MockProvider
from app.web.service import ClassroomService
from tests.f3_helpers import one_material_request, wait_until


def test_two_sessions_do_not_share_history_material_or_messages(tmp_path):
    service = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: MockProvider(),
    )
    a, _ = service.create_session(one_material_request("iso-a", lesson="A", timeout=30))
    b, _ = service.create_session(one_material_request("iso-b", lesson="B", timeout=30))
    aid, bid = a["sessionId"], b["sessionId"]

    wait_until(lambda: len(service.get_events(aid)) >= 1)
    wait_until(lambda: len(service.get_events(bid)) >= 1)
    service.send_message(aid, "A 专属问题？")
    service.send_message(bid, "B 专属问题？")
    wait_until(lambda: len(service.get_events(aid)) >= 2)
    wait_until(lambda: len(service.get_events(bid)) >= 2)

    ae = service.get_events(aid)
    be = service.get_events(bid)
    assert ae[1]["trigger"]["content"] == "A 专属问题？"
    assert be[1]["trigger"]["content"] == "B 专属问题？"
    assert all(e["sessionId"] == aid for e in ae)
    assert all(e["sessionId"] == bid for e in be)

    ar = service._sessions[aid]
    br = service._sessions[bid]
    assert ar.classroom.state is not br.classroom.state
    assert ar.materials is not br.materials
    service.end(aid)
    service.end(bid)
