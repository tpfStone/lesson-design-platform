"""A 类验证: 基于 MockProvider 的确定性场景测试。

用普通 pytest 即可运行，不依赖真实 API:
    python -m pytest tests/test_validation_mock.py -v

验证: 流程正确性 / 不崩溃 / 权限校验 / 状态更新 / 轨迹生成 / 轮数上限保护。
"""
from tests.validation.criteria import (
    evaluate_negative_emotion,
    evaluate_off_topic,
    evaluate_progression,
)
from tests.validation.trace import compact_trace

from app.classroom.classroom import Classroom
from app.llm.mock import MockProvider
from tests.validation.runner import run_scenario

NEGATIVE_MSG = "这个太难了，我完全听不懂，也不想继续学了。"
OFFTOPIC_MSG = "先别讲 LLM 了，我们聊聊最近有什么好玩的游戏吧。"
PROGRESSION_MAX_TURNS = 40


def make_classroom(tmp_path):
    return Classroom(llm=MockProvider(), input_fn=lambda *a: "",
                     log_dir=str(tmp_path))


# ---------- 负面情绪 ----------

def test_negative_emotion_mock(tmp_path):
    result = run_scenario(make_classroom(tmp_path),
                          user_message=NEGATIVE_MSG, max_turns=4)
    verdict = evaluate_negative_emotion(result)
    assert verdict.passed, verdict.failures
    # 行为约束而非具体 speaker: 只要出现支持性行为即可
    supportive = [r for r in result.records if r["function"] == "encourage"]
    assert supportive, "MockProvider 应选择 encourage"
    assert result.final_status in {"active", "finished"}


# ---------- 跑题重定向 ----------

def test_off_topic_mock(tmp_path):
    result = run_scenario(make_classroom(tmp_path),
                          user_message=OFFTOPIC_MSG, max_turns=4)
    verdict = evaluate_off_topic(result)
    assert verdict.passed, verdict.failures
    redirects = [r for r in result.records if r["function"] == "redirect"]
    assert redirects, "MockProvider 应选择 redirect"
    # redirect 当轮不得跳过当前材料
    assert redirects[0]["current_material_after"] == redirects[0]["current_material_before"]


# ---------- 连续推进 ----------

def test_progression_mock(tmp_path):
    result = run_scenario(make_classroom(tmp_path),
                          max_turns=PROGRESSION_MAX_TURNS)
    verdict = evaluate_progression(result)
    assert verdict.passed, verdict.failures
    transitions = [r for r in result.records
                   if r["current_material_before"] != r["current_material_after"]]
    assert len(transitions) >= 1
    # Mock 场景是确定性的: 5 份材料全部推进完并正常下课
    assert result.finished
    assert len(transitions) == 5


def test_progression_max_turn_safety(tmp_path):
    """轮数上限必须安全截断验证运行；轮数不足时判据显式 FAIL 而非静默通过。"""
    result = run_scenario(make_classroom(tmp_path), max_turns=2)
    assert not result.crashed
    assert len(result.records) == 2
    assert result.final_status == "active"  # 上限生效，未失控
    verdict = evaluate_progression(result)
    assert not verdict.passed  # 2 轮内无材料推进 → FAIL
    assert any("No material transition" in f for f in verdict.failures)


# ---------- 轨迹工具 ----------

def test_trace_record_fields_and_compact_output(tmp_path):
    result = run_scenario(make_classroom(tmp_path),
                          user_message=NEGATIVE_MSG, max_turns=2)
    required = {"turn_id", "current_material_before", "speaker", "function",
                "reason", "validation_status", "current_material_after",
                "session_status"}
    for r in result.records:
        assert required <= set(r), f"trace 缺少字段: {required - set(r)}"

    text = compact_trace(result.records)
    assert "Turn 1" in text
    assert "Decision: " in text
    assert "Material: What is an LLM?" in text


def test_infinite_repetition_detection(tmp_path):
    """连续相同决策超过阈值时，判据必须给出准确失败原因。"""
    from tests.validation.runner import ScenarioResult
    from tests.validation.criteria import evaluate_progression

    fake = ScenarioResult(records=[
        {"turn_id": i + 1, "current_material_before": "M1",
         "speaker": "deep_thinker", "function": "discuss", "reason": "",
         "validation_status": "ok", "current_material_after": "M1",
         "session_status": "active"}
        for i in range(8)
    ], final_status="active")
    verdict = evaluate_progression(fake)
    assert not verdict.passed
    assert any("repeated 8 times consecutively" in f for f in verdict.failures)
