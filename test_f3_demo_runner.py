from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return load_module("f3_demo_runner_under_test", HERE / "run_f3_demo.py")


def valid_config(tmp_path: Path):
    return {
        "f4Url": "http://f4",
        "f3Url": "http://f3",
        "lessonId": "F2-LESSON",
        "versionId": "F2-VERSION",
        "f4SessionId": "F4-SESSION",
        "rounds": 4,
        "messages": ["m1", "m2", "m3", "m4"],
        "outputDir": str(tmp_path / "out"),
    }


def test_valid_config_can_be_loaded(runner, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(valid_config(tmp_path)), encoding="utf-8")
    loaded = runner.load_config(path)
    assert loaded["rounds"] == 4
    assert loaded["lessonId"] == "F2-LESSON"


@pytest.mark.parametrize("rounds", [0, 11])
def test_rounds_out_of_range_fail(runner, tmp_path, rounds):
    data = valid_config(tmp_path)
    data["rounds"] = rounds
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="rounds"):
        runner.load_config(path)


def test_messages_less_than_rounds_fail(runner, tmp_path):
    data = valid_config(tmp_path)
    data["messages"] = ["m1"]
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="messages"):
        runner.load_config(path)


class FakeResponse:
    def __init__(self, status_code=200, data=None, text=None):
        self.status_code = status_code
        self._data = data
        self.text = text if text is not None else json.dumps(data or {})
        self.ok = 200 <= status_code < 300

    def json(self):
        if self._data is _INVALID_JSON:
            raise ValueError("invalid json")
        return self._data

    def raise_for_status(self):
        if not self.ok:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")


_INVALID_JSON = object()


class FakeHTTPSession:
    def __init__(self, fail_message_round=None):
        self.fail_message_round = fail_message_round
        self.message_calls = 0
        self.f3_session_id = "F3-SESSION-12345678"
        self.history = []
        self.start_payload = None
        self.f4_state = {
            "session": {"id": "F4-SESSION", "config_snapshot": {"provider": "mock"}},
            "lesson_plan": {"id": "F4-PLAN"},
            "sections": [
                {"id": "S2", "title": "探究", "section_type": "exploration", "order_index": 2, "current_content": "探究正文"},
                {"id": "S1", "title": "导入", "section_type": "introduction", "order_index": 1, "current_content": "导入正文"},
            ],
        }

    def get(self, url, timeout=None):
        if url.endswith("/api/health"):
            return FakeResponse(200, {"status": "ok"})
        if url.endswith("/health"):
            return FakeResponse(200, {"status": "up", "service": "F3 Classroom API", "version": "2.1"})
        if "/api/sessions/F4-SESSION/current-state" in url:
            return FakeResponse(200, self.f4_state)
        if f"/api/classroom/{self.f3_session_id}/state" in url:
            return FakeResponse(200, {
                "session_id": self.f3_session_id,
                "lesson_id": "F2-LESSON",
                "version_id": "F2-VERSION",
                "source": {"module": "F4", "session_id": "F4-SESSION", "lesson_plan_id": "F4-PLAN"},
                "status": "active",
                "history": list(self.history),
            })
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url, json=None, timeout=None):
        if url.endswith("/api/classroom/start"):
            self.start_payload = json
            return FakeResponse(200, {
                "session_id": self.f3_session_id,
                "status": "started",
                "lesson_id": json["lesson_id"],
                "version_id": json["version_id"],
                "source": json["source"],
                "material_count": len(json["materials"]),
            })
        if url.endswith("/api/classroom/message"):
            self.message_calls += 1
            if self.fail_message_round == self.message_calls:
                return FakeResponse(500, {"detail": "boom"})
            message = json["message"]
            self.history.append({"speaker": "user", "function": "user_message", "content": message})
            reply = {"speaker": "teacher", "function": "teach", "content": f"[MockLLM] reply {self.message_calls}"}
            self.history.append(reply)
            return FakeResponse(200, reply)
        raise AssertionError(f"unexpected POST {url}")


def test_runner_uses_f2_ids_and_executes_exact_n_rounds(runner, tmp_path):
    config = valid_config(tmp_path)
    http = FakeHTTPSession()
    result = runner.run_demo(config, http_session=http)
    assert result["status"] == "COMPLETED"
    assert result["completedRounds"] == 4
    assert http.message_calls == 4
    assert http.start_payload["lesson_id"] == "F2-LESSON"
    assert http.start_payload["version_id"] == "F2-VERSION"
    assert http.start_payload["source"]["lesson_plan_id"] == "F4-PLAN"


def test_each_round_saves_input_response_and_state_snapshot(runner, tmp_path):
    result = runner.run_demo(valid_config(tmp_path), http_session=FakeHTTPSession())
    assert len(result["rounds"]) == 4
    for index, item in enumerate(result["rounds"], 1):
        assert item["round"] == index
        assert item["input"]
        assert set(item["response"]) >= {"speaker", "function", "content"}
        assert item["stateSnapshot"]["session_id"] == "F3-SESSION-12345678"
        assert item["historyCount"] == index * 2


def test_success_generates_json_and_markdown(runner, tmp_path):
    result = runner.run_demo(valid_config(tmp_path), http_session=FakeHTTPSession())
    record_path = Path(result["sessionRecordPath"])
    summary_path = Path(result["summaryPath"])
    assert record_path.exists()
    assert summary_path.exists()
    saved = json.loads(record_path.read_text(encoding="utf-8"))
    assert saved["status"] == "COMPLETED"
    assert "F3 课堂模拟简报" in summary_path.read_text(encoding="utf-8")


def test_output_directory_does_not_overwrite_previous_run(runner, tmp_path, monkeypatch):
    fixed = runner.datetime.fromisoformat("2026-10-02T22:30:00+08:00")
    first = runner.create_run_dir(str(tmp_path / "out"), "abcdefgh-1", when=fixed)
    second = runner.create_run_dir(str(tmp_path / "out"), "abcdefgh-1", when=fixed)
    assert first != second
    assert first.exists() and second.exists()


def test_middle_http_failure_writes_failed_result_and_keeps_completed_rounds(runner, tmp_path):
    result = runner.run_demo(valid_config(tmp_path), http_session=FakeHTTPSession(fail_message_round=3))
    assert result["status"] == "FAILED"
    assert result["completedRounds"] == 2
    assert result["error"]["round"] == 3
    saved = json.loads(Path(result["sessionRecordPath"]).read_text(encoding="utf-8"))
    assert saved["status"] == "FAILED"
    summary = Path(result["summaryPath"]).read_text(encoding="utf-8")
    assert "## 失败信息" in summary
    assert "运行状态：**FAILED**" in summary


def test_five_identity_mappings_are_consistent(runner, tmp_path):
    result = runner.run_demo(valid_config(tmp_path), http_session=FakeHTTPSession())
    assert result["lessonId"] == "F2-LESSON"
    assert result["versionId"] == "F2-VERSION"
    assert result["f4SessionId"] == "F4-SESSION"
    assert result["f4LessonPlanId"] == "F4-PLAN"
    assert result["f3SessionId"] == "F3-SESSION-12345678"
    assert result["finalState"]["source"]["session_id"] == "F4-SESSION"


def test_mock_real_boundary_in_json_and_markdown(runner, tmp_path):
    result = runner.run_demo(valid_config(tmp_path), http_session=FakeHTTPSession())
    assert result["executionBoundary"]["httpChain"] == "REAL"
    assert result["executionBoundary"]["f4Provider"] == "mock"
    assert result["executionBoundary"]["f3ModelContent"] == "MOCK"
    summary = Path(result["summaryPath"]).read_text(encoding="utf-8")
    assert "HTTP 链路：`REAL`" in summary
    assert "F3 模型内容：`MOCK`" in summary


def test_health_returns_up(monkeypatch):
    class FakeEntry:
        pass

    class FakeClassroom:
        def __init__(self, materials):
            self.state = types.SimpleNamespace(session_status="active", dialogue_history=[])
        def step(self, message):
            return None

    app_pkg = types.ModuleType("app")
    classroom_pkg = types.ModuleType("app.classroom")
    classroom_v2_mod = types.ModuleType("app.classroom.classroom_v2")
    classroom_mod = types.ModuleType("app.classroom.classroom")
    classroom_mod.Classroom = FakeClassroom
    monkeypatch.setitem(sys.modules, "app", app_pkg)
    monkeypatch.setitem(sys.modules, "app.classroom", classroom_pkg)
    monkeypatch.setitem(sys.modules, "app.classroom.classroom_v2", classroom_v2_mod)
    monkeypatch.setitem(sys.modules, "app.classroom.classroom", classroom_mod)

    api = load_module("health_classroom_api", HERE / "classroom_api.py")
    client = TestClient(api.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "up", "service": "F3 Classroom API", "version": "2.1"}


class FakeF2Session:
    def __init__(self, status_code=201, already_saved=False):
        self.status_code = status_code
        self.already_saved = already_saved
        self.posts = []

    def post(self, url, json=None, timeout=None):
        self.posts.append({"url": url, "json": json, "timeout": timeout})
        if self.status_code not in (200, 201):
            return FakeResponse(self.status_code, {"code": "FAIL"}, text="writeback failed")
        record = json["sessionRecord"]
        return FakeResponse(self.status_code, {
            "simulationRunId": "01SIMULATION000000000000000",
            "lessonId": record["lessonId"],
            "versionId": record["versionId"],
            "f3SessionId": record["f3SessionId"],
            "status": record["status"],
            "completedRounds": record["completedRounds"],
            "alreadySaved": self.already_saved,
            "createdAt": "2026-10-03T01:30:00Z",
        })


def writeback_config(tmp_path: Path):
    config = valid_config(tmp_path)
    config["f2Url"] = "http://f2:8080"
    config["writebackToF2"] = True
    return config


def make_local_success(runner, tmp_path: Path):
    config = writeback_config(tmp_path)
    result = runner.run_demo(config, http_session=FakeHTTPSession())
    return config, result, Path(result["sessionRecordPath"]).parent


def test_writeback_false_keeps_existing_runner_behavior(runner, tmp_path):
    data = valid_config(tmp_path)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = runner.load_config(path)
    assert loaded["writebackToF2"] is False
    result = runner.run_demo(loaded, http_session=FakeHTTPSession())
    assert result["status"] == "COMPLETED"
    assert not (Path(result["sessionRecordPath"]).parent / "f2_writeback_receipt.json").exists()


def test_f2_writeback_path_and_payload_are_correct(runner, tmp_path):
    config, result, run_dir = make_local_success(runner, tmp_path)
    f2 = FakeF2Session()
    receipt = runner.writeback_to_f2(config, run_dir, http_session=f2)
    assert len(f2.posts) == 1
    call = f2.posts[0]
    assert call["url"] == "http://f2:8080/api/platform/lessons/F2-LESSON/simulations"
    assert call["json"]["sessionRecord"]["f3SessionId"] == result["f3SessionId"]
    assert "F3 课堂模拟简报" in call["json"]["summaryMarkdown"]
    assert receipt["lessonId"] == "F2-LESSON"


def test_successful_writeback_generates_receipt(runner, tmp_path):
    config, result, run_dir = make_local_success(runner, tmp_path)
    receipt = runner.writeback_to_f2(config, run_dir, http_session=FakeF2Session())
    path = run_dir / "f2_writeback_receipt.json"
    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["simulationRunId"] == "01SIMULATION000000000000000"
    assert saved["f3SessionId"] == result["f3SessionId"]
    assert saved["alreadySaved"] is False
    assert saved["writtenBackAt"]


def test_writeback_failure_preserves_json_md_and_raises(runner, tmp_path):
    config, result, run_dir = make_local_success(runner, tmp_path)
    record_path = Path(result["sessionRecordPath"])
    summary_path = Path(result["summaryPath"])
    before_record = record_path.read_text(encoding="utf-8")
    before_summary = summary_path.read_text(encoding="utf-8")
    with pytest.raises(RuntimeError, match="模拟已完成、F2 保存失败"):
        runner.writeback_to_f2(config, run_dir, http_session=FakeF2Session(status_code=500))
    assert record_path.read_text(encoding="utf-8") == before_record
    assert summary_path.read_text(encoding="utf-8") == before_summary
    assert not (run_dir / "f2_writeback_receipt.json").exists()


def test_writeback_only_uses_existing_files_without_f3_calls(runner, tmp_path):
    config, result, run_dir = make_local_success(runner, tmp_path)
    f2 = FakeF2Session()
    receipt = runner.writeback_to_f2(config, run_dir, http_session=f2)
    assert len(f2.posts) == 1
    assert receipt["f3SessionId"] == result["f3SessionId"]
    # writeback_to_f2 only reads local artifacts and performs the single F2 POST above;
    # it has no F3 URL access path.


def test_idempotent_f2_response_is_recorded_in_receipt(runner, tmp_path):
    config, _, run_dir = make_local_success(runner, tmp_path)
    receipt = runner.writeback_to_f2(
        config, run_dir, http_session=FakeF2Session(status_code=200, already_saved=True)
    )
    assert receipt["alreadySaved"] is True
    saved = json.loads((run_dir / "f2_writeback_receipt.json").read_text(encoding="utf-8"))
    assert saved["alreadySaved"] is True


def test_writeback_does_not_rewrite_original_session_record(runner, tmp_path):
    config, result, run_dir = make_local_success(runner, tmp_path)
    record_path = Path(result["sessionRecordPath"])
    original = record_path.read_bytes()
    runner.writeback_to_f2(config, run_dir, http_session=FakeF2Session())
    assert record_path.read_bytes() == original
