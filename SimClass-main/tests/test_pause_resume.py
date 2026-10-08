"""暂停/恢复状态机的回归测试（MockProvider，无 API 依赖）。

针对的 bug: 旧实现用 consecutive_timeout_count >= MAX 判断暂停，
且 empty_enter 不清零计数，导致暂停后空回车只能单步推进、无法恢复自主模式。

模型:
    AUTONOMOUS --timeout 达到 MAX--> PAUSED_FOR_USER
    PAUSED_FOR_USER --user_input / empty_enter--> AUTONOMOUS（计数清零，新周期）

事件源收到的 timeout 参数可直接验证恢复行为:
    15.0 = 自主 τ 等待；None = PAUSED 阻塞等待。
"""
from app.classroom.classroom import Classroom
from app.classroom.events import (
    TRIGGER_EMPTY_ENTER,
    TRIGGER_TIMEOUT,
    TRIGGER_USER_INPUT,
    ClassroomEvent,
)
from app.llm.mock import MockProvider

TAU = 15.0  # Classroom 默认 timeout_seconds


def make_classroom(event_fn, tmp_path, max_timeouts=3):
    return Classroom(llm=MockProvider(), event_fn=event_fn,
                     log_dir=str(tmp_path),
                     max_consecutive_timeouts=max_timeouts)


def timeout_script(*steps, repeat_timeout=None):
    """steps: 依次返回的事件; repeat_timeout=N 表示之后继续返回 timeout。
    记录每次 event_fn 收到的 timeout 参数（None=PAUSED 阻塞等待）。"""
    seen = []

    def event_fn(timeout):
        seen.append(timeout)
        n = len(seen)
        if n <= len(steps):
            ev = steps[n - 1]
        elif repeat_timeout is not None and n <= repeat_timeout:
            ev = ClassroomEvent(TRIGGER_TIMEOUT)
        else:
            return None  # quit
        return ev if isinstance(ev, ClassroomEvent) else ev()

    return event_fn, seen


# ---------- Test 1: 三连超时进入暂停 ----------

def test_three_consecutive_timeouts_enter_pause(tmp_path):
    event_fn, seen = timeout_script(
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
    )
    classroom = make_classroom(event_fn, tmp_path, max_timeouts=3)
    classroom.run()
    assert seen == [TAU, TAU, TAU, None]   # 第 4 次等待是 PAUSED 阻塞等待
    assert classroom.state.consecutive_timeout_count == 3
    assert classroom.state.autonomous_mode is False
    records = classroom.logger.records
    assert records[-1]["trigger_type"] == "timeout"
    assert records[-1]["consecutive_timeout_count"] == 3
    assert records[-1]["autonomous_mode"] is False   # 暂停可从日志复原


# ---------- Test 2: 暂停 + 空回车恢复 ----------

def test_paused_empty_enter_resumes(tmp_path, capsys):
    event_fn, seen = timeout_script(
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_EMPTY_ENTER),
    )
    classroom = make_classroom(event_fn, tmp_path, max_timeouts=3)
    classroom.run()
    assert seen == [TAU, TAU, TAU, None, TAU]  # 空回车后重新启用 τ 等待

    r = classroom.logger.records[4]  # 空回车轮（init + 3 个 timeout 之后）
    assert r["trigger_type"] == "empty_enter"    # 不被归类为 user_input
    assert r["user_message"] is None             # 不伪造用户消息
    assert not any(e.speaker == "user"
                   for e in classroom.state.dialogue_history)
    assert r["consecutive_timeout_count"] == 0   # 计数清零
    assert r["autonomous_mode"] is True          # 暂停状态清除
    assert classroom.state.autonomous_mode is True

    out = capsys.readouterr().out
    assert "[PAUSED]" in out and "[RESUMED]" in out


# ---------- Test 3: 暂停 + 有意义输入恢复 ----------

def test_paused_user_input_resumes(tmp_path):
    event_fn, seen = timeout_script(
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_USER_INPUT,
                               user_message="老师，什么是 Attention？"),
    )
    classroom = make_classroom(event_fn, tmp_path, max_timeouts=3)
    classroom.run()
    assert seen == [TAU, TAU, TAU, None, TAU]  # 输入后重新启用 τ 等待

    r = classroom.logger.records[4]  # 用户输入轮（init + 3 个 timeout 之后）
    assert r["trigger_type"] == "user_input"
    assert r["user_message"] == "老师，什么是 Attention？"
    assert r["consecutive_timeout_count"] == 0
    assert r["autonomous_mode"] is True
    assert r["function"] == "answer_question"   # Manager 处理了问题
    assert any(e.speaker == "user" and "Attention" in e.content
               for e in classroom.state.dialogue_history)


# ---------- Test 4: 精确回归 —— 空回车后 timeout 自动恢复 ----------

def test_regression_timeout_resumes_after_empty_enter(tmp_path):
    # MAX=3: T,T,T -> pause -> 空回车 -> Manager 动作 -> 等 τ -> timeout 自动发生
    event_fn, seen = timeout_script(
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_EMPTY_ENTER),
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),  # 新周期的 timeout #1
    )
    classroom = make_classroom(event_fn, tmp_path, max_timeouts=3)
    classroom.run()
    # 旧 bug 在此处: seen[4] 会是 None（空回车后再次暂停，timeout 不再自动发生）
    assert seen == [TAU, TAU, TAU, None, TAU, TAU]  # 末尾仍是 τ 等待
    triggers = [r["trigger_type"] for r in classroom.logger.records]
    assert triggers == ["initialization", "timeout", "timeout", "timeout",
                        "empty_enter", "timeout"]
    # 新周期计数从 1 重新开始，且未再次进入暂停
    assert classroom.logger.records[5]["consecutive_timeout_count"] == 1
    assert classroom.logger.records[5]["autonomous_mode"] is True
    assert classroom.state.autonomous_mode is True


# ---------- Test 5: 精确回归 —— 有意义输入后 timeout 自动恢复 ----------

def test_regression_timeout_resumes_after_user_input(tmp_path):
    event_fn, seen = timeout_script(
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_USER_INPUT, user_message="继续讲"),
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),  # 恢复后的 timeout #1
    )
    classroom = make_classroom(event_fn, tmp_path, max_timeouts=3)
    classroom.run()
    assert seen == [TAU, TAU, TAU, None, TAU, TAU]
    triggers = [r["trigger_type"] for r in classroom.logger.records]
    assert triggers == ["initialization", "timeout", "timeout", "timeout",
                        "user_input", "timeout"]
    assert classroom.logger.records[5]["consecutive_timeout_count"] == 1
    assert classroom.logger.records[5]["autonomous_mode"] is True


# ---------- Test 6: 恢复后新一轮允许三个新超时才再次暂停 ----------

def test_new_cycle_allows_three_timeouts_before_next_pause(tmp_path):
    event_fn, seen = timeout_script(
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_TIMEOUT),
        lambda: ClassroomEvent(TRIGGER_EMPTY_ENTER),  # 恢复
        repeat_timeout=7,  # 第 5-7 次等待继续返回 timeout（新周期 #1 #2 #3）
    )
    classroom = make_classroom(event_fn, tmp_path, max_timeouts=3)
    classroom.run()
    # T,T,T | PAUSED 阻塞 | T,T,T | 第二次 PAUSED 阻塞 | quit
    assert seen == [TAU, TAU, TAU, None, TAU, TAU, TAU, None]
    records = classroom.logger.records
    triggers = [r["trigger_type"] for r in records]
    assert triggers == ["initialization", "timeout", "timeout", "timeout",
                       "empty_enter", "timeout", "timeout", "timeout"]
    # 新周期的三个 timeout 计数为 1/2/3（不是 4/5/6）
    new_cycle = records[5:]
    assert [r["consecutive_timeout_count"] for r in new_cycle] == [1, 2, 3]
    # 第 6 个 timeout（新周期第 3 个）再次进入暂停
    assert new_cycle[2]["autonomous_mode"] is False
    assert classroom.state.consecutive_timeout_count == 3
    assert classroom.state.autonomous_mode is False
