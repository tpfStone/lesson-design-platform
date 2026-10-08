from fastapi.testclient import TestClient

from app.api import classroom_api
from app.llm.mock import MockProvider
from app.web.service import ClassroomService
from tests.f3_helpers import wait_until


def test_formal_api_contract_and_idempotency(tmp_path, monkeypatch):
    test_service = ClassroomService(
        storage_root=tmp_path,
        llm_factory=lambda mode: MockProvider(),
    )
    monkeypatch.setattr(classroom_api, "service", test_service)
    client = TestClient(classroom_api.app)

    payload = {
        "lessonId": "L1",
        "versionId": "V1",
        "modelMode": "MOCK",
        "requestKey": "api-key-1",
        "timeoutSeconds": 30,
        "maxConsecutiveTimeouts": 5,
        "maxEvents": 20,
        "maxWallClockSeconds": 30,
        "materials": [
            {
                "materialId": "m1",
                "title": "定义",
                "teachingScript": "脚本",
                "keyPoints": ["要点"],
                "sourceSectionId": "sec1",
            }
        ],
    }
    r = client.post("/api/classroom/sessions", json=payload)
    assert r.status_code == 201
    body = r.json()
    sid = body["sessionId"]
    assert body["modelMode"] == "MOCK"
    assert body["lessonId"] == "L1"

    r2 = client.post("/api/classroom/sessions", json=payload)
    assert r2.status_code == 200
    assert r2.json()["sessionId"] == sid
    assert r2.json()["idempotentReplay"] is True

    assert client.get("/api/health").status_code == 200
    assert client.get(f"/api/classroom/sessions/{sid}").status_code == 200
    assert client.get(f"/api/classroom/sessions/{sid}/events").status_code == 200
    assert client.patch(
        f"/api/classroom/sessions/{sid}/settings", json={"timeoutSeconds": 20}
    ).status_code == 200
    assert client.post(f"/api/classroom/sessions/{sid}/pause").json()["status"] == "PAUSED"
    assert client.post(
        f"/api/classroom/sessions/{sid}/messages", json={"message": "问题？"}
    ).status_code == 202
    assert client.post(f"/api/classroom/sessions/{sid}/resume").status_code == 200
    assert client.post(f"/api/classroom/sessions/{sid}/end").status_code == 200
    wait_until(lambda: test_service.get_session(sid)["status"] == "INTERRUPTED", timeout=2)
    assert client.get(f"/api/classroom/sessions/{sid}/result").status_code == 200
    assert client.get(
        f"/api/classroom/sessions/{sid}/artifacts/session_record"
    ).status_code == 200
