"""Timeout τ 触发机制的确定性测试（MockProvider，无 API 依赖）。

验证:
1. user_input 触发 Manager 决策
2. timeout 触发 Manager 决策
3. timeout 不伪造用户消息
4. timeout 递增 consecutive_timeout_count
5. user_input 重置计数
6. Manager 决策上下文包含 trigger_type
7. timeout 走同一条 Manager -> Executor 管线
8. 连续超时上限保护（暂停自主推进）
9. 反复 timeout 后课堂保持稳定
"""
import json

from app.classroom.classroom import Classroom
from app.classroom.events import (
    TRIGGER_EMPTY_ENTER,
    TRIGGER_TIMEOUT,
    TRIGGER_USER_INPUT,
    ClassroomEvent,
)
from app.llm.mock import MockProvider
from helpers import ScriptedLLM


def make_classroom(event_fn, tmp_path, max_timeouts=3, llm=None):
    return Classroom(llm=llm or MockProvider(), event_fn=event_fn,
                     log_dir=str(tmp_path),
                     max_consecutive_timeouts=max_timeouts)


def scripted_events(events):
    """按脚本依次返回事件，耗尽后返回 None（等价 quit）。"""
    seq = iter(events)
    return lambda timeout: next(seq, None)


# ---------- 1. user_input 触发 ----------

def test_user_input_triggers_manager_decision(tmp_path):
    classroom = make_classroom(scripted_events([
        ClassroomEvent(TRIGGER_USER_INPUT,
                       user_message="Transformer 和 RNN 有什么区别？"),
    ]), tmp_path)
    classroom.run()
    history = classroom.state.dialogue_history
    assert any(e.speaker == "user" for e in history)      # 用户消息进入历史
    assert any(e.function == "answer_question" for e in history)  # Manager 做出响应
    records = classroom.logger.records
    assert records[0]["trigger_type"] == "initialization"  # 首轮 initialization
    assert any(r["trigger_type"] == "user_input" for r in records)


# ---------- 2. timeout 触发 ----------

def test_timeout_triggers_manager_decision(tmp_path):
    classroom = make_classroom(scripted_events([ClassroomEvent(TRIGGER_TIMEOUT)]),
                               tmp_path)
    classroom.run()
    timeout_records = [r for r in classroom.logger.records
                       if r["trigger_type"] == "timeout"]
    assert timeout_records, "timeout 必须能触发 Manager 决策"
    # Mock 决策: teach 后静默 -> inquisitive_mind 提问（动态，非硬编码）
    assert timeout_records[0]["speaker"] == "inquisitive_mind"
    assert timeout_records[0]["function"] == "ask_question"


# ---------- 3. timeout 不伪造用户消息 ----------

def test_timeout_does_not_fabricate_user_text(tmp_path):
    classroom = make_classroom(scripted_events([ClassroomEvent(TRIGGER_TIMEOUT)]),
                               tmp_path)
    classroom.run()
    assert classroom.state.pending_user_message is None
    assert not any(e.speaker == "user"
                   for e in classroom.state.dialogue_history)
    r = next(r for r in classroom.logger.records
             if r["trigger_type"] == "timeout")
    assert r["user_message"] is None


# ---------- 4. timeout 递增连续计数 ----------

def test_timeout_increments_consecutive_count(tmp_path):
    classroom = make_classroom(scripted_events(
        [ClassroomEvent(TRIGGER_TIMEOUT)] * 2), tmp_path)
    classroom.run()
    assert classroom.state.consecutive_timeout_count == 2
    assert classroom.state.last_trigger_type == "timeout"


# ---------- 5. user_input 重置连续计数 ----------

def test_user_input_resets_consecutive_count(tmp_path):
    classroom = make_classroom(scripted_events([
        ClassroomEvent(TRIGGER_TIMEOUT),
        ClassroomEvent(TRIGGER_TIMEOUT),
        ClassroomEvent(TRIGGER_USER_INPUT, user_message="这里没懂，再讲讲？"),
        ClassroomEvent(TRIGGER_TIMEOUT),
    ]), tmp_path)
    classroom.run()
    # 2 次超时 -> user_input 清零 -> 1 次超时 -> 最终为 1
    assert classroom.state.consecutive_timeout_count == 1


# ---------- 6. Manager 上下文包含 trigger_type ----------

def test_manager_brief_receives_trigger_type(tmp_path):
    def d(speaker, function):
        return json.dumps({"speaker": speaker, "function": function,
                           "reason": "r", "end_class": False}, ensure_ascii=False)

    scripted = ScriptedLLM([
        d("teacher", "teach"),        # init 轮: Manager
        "（教学发言）",                # init 轮: Agent
        d("inquisitive_mind", "ask_question"),  # timeout 轮: Manager
        "（同学提问）",                # timeout 轮: Agent
    ])
    classroom = make_classroom(scripted_events([ClassroomEvent(TRIGGER_TIMEOUT)]),
                              tmp_path, llm=scripted)
    classroom.run()
    # 第 3 次 LLM 调用是 timeout 轮的 Manager 请求
    manager_messages = scripted.calls[2]
    brief = manager_messages[1]["content"]
    assert "trigger_type" in brief and "timeout" in brief
    assert "consecutive_timeout_count" in brief


# ---------- 7. timeout 走同一条 Manager -> Executor 管线 ----------

def test_timeout_enters_same_manager_executor_pipeline(tmp_path):
    classroom = make_classroom(scripted_events([ClassroomEvent(TRIGGER_TIMEOUT)]),
                               tmp_path)
    classroom.run()
    # timeout 轮同样产出: 决策 + 执行 + 状态更新（发言进历史）
    r = next(r for r in classroom.logger.records
             if r["trigger_type"] == "timeout")
    assert r["speaker"] and r["function"] and r["response"]
    entry = next(e for e in classroom.state.dialogue_history
                 if e.function == "ask_question")
    assert entry.speaker == "inquisitive_mind"
    assert classroom.state.last_speaker == entry.speaker


# ---------- 8. 连续超时上限保护 ----------

def test_max_consecutive_timeout_protection(tmp_path):
    calls = {"timeout": 0, "blocking": 0, "streak": 0, "max_streak": 0}

    def event_fn(timeout):
        if timeout is None:
            # 暂停后的阻塞等待: 只接受真实用户输入（打断连续超时链）
            calls["blocking"] += 1
            calls["streak"] = 0
            return ClassroomEvent(TRIGGER_USER_INPUT, user_message="我回来了，继续讲")
        calls["timeout"] += 1
        calls["streak"] += 1
        calls["max_streak"] = max(calls["max_streak"], calls["streak"])
        if calls["timeout"] > 6:
            return None  # 结束 demo
        return ClassroomEvent(TRIGGER_TIMEOUT)

    classroom = make_classroom(event_fn, tmp_path, max_timeouts=3)
    classroom.run()
    # 连续超时从未超过上限 3
    assert calls["max_streak"] <= 3
    # 6 次超时 = 3+3，两次到达上限 -> 两次进入阻塞等待并被用户输入打断
    assert calls["blocking"] == 2
    assert classroom.state.session_status == "finished"
    # 暂停后再无 timeout 事件越过上限（最终计数已被 user_input 重置）
    assert classroom.state.consecutive_timeout_count == 0


# ---------- 9. 反复 timeout 后课堂稳定 ----------

def test_classroom_stable_after_repeated_timeouts(tmp_path):
    events = []
    for _ in range(3):
        events.append(ClassroomEvent(TRIGGER_TIMEOUT))
        events.append(ClassroomEvent(TRIGGER_USER_INPUT, user_message="继续"))
    events.append(ClassroomEvent(TRIGGER_TIMEOUT))
    classroom = make_classroom(scripted_events(events), tmp_path)
    classroom.run()
    assert classroom.state.session_status == "finished"
    assert classroom.state.material_index >= 1          # 材料确有推进
    records = classroom.logger.records
    assert all(r["trigger_type"] for r in records)      # 每轮 trigger 可追溯
    assert sum(1 for r in records
               if r["trigger_type"] == "timeout") == 4


# ---------- 附: 空回车与 timeout 是不同 trigger ----------

def test_empty_enter_is_distinct_from_timeout(tmp_path):
    classroom = make_classroom(scripted_events(
        [ClassroomEvent(TRIGGER_EMPTY_ENTER)]), tmp_path)
    classroom.run()
    r = classroom.logger.records[1]  # 首轮是 initialization
    assert r["trigger_type"] == "empty_enter"
    assert classroom.state.consecutive_timeout_count == 0  # 不计入超时
