"""Test 4-8 相关: Manager 决策（LLM-powered + 校验 / retry / fallback）。"""
import json

from app.agents import AGENT_CLASSES
from app.controller.manager import Manager
from app.controller.state import ClassState
from app.materials import load_materials
from helpers import ScriptedLLM

ROLES = ["teacher", "assistant", "class_clown", "deep_thinker",
         "note_taker", "inquisitive_mind"]


def make_manager(scripted: ScriptedLLM):
    agents = {cls.name: cls(scripted) for cls in AGENT_CLASSES}
    state = ClassState(load_materials(), list(agents.keys()))
    return Manager(scripted, agents), state


def decision_json(speaker, function, reason="test", end_class=False):
    return json.dumps({"speaker": speaker, "function": function,
                       "reason": reason, "end_class": end_class},
                      ensure_ascii=False)


def test_manager_chooses_assistant_answer_question():  # Test 4
    scripted = ScriptedLLM([decision_json("assistant", "answer_question")])
    manager, state = make_manager(scripted)
    state.add_user_message("Transformer 为什么比 RNN 更适合处理长距离依赖？")
    d = manager.decide(state)
    assert (d.speaker, d.function) == ("assistant", "answer_question")
    # Manager prompt 必须观察到用户消息
    assert any("Transformer" in m["content"]
               for call in scripted.calls for m in call)


def test_manager_chooses_deep_thinker_ask_question():  # Test 5
    scripted = ScriptedLLM([decision_json("deep_thinker", "ask_question")])
    manager, state = make_manager(scripted)
    d = manager.decide(state)
    assert (d.speaker, d.function) == ("deep_thinker", "ask_question")


def test_manager_chooses_note_taker_summarize():  # Test 6
    scripted = ScriptedLLM([decision_json("note_taker", "summarize")])
    manager, state = make_manager(scripted)
    state.mark_taught()
    d = manager.decide(state)
    assert (d.speaker, d.function) == ("note_taker", "summarize")


def test_manager_handles_negative_emotion():  # Test 7
    scripted = ScriptedLLM([decision_json("assistant", "encourage",
                                          "用户情绪低落")])
    manager, state = make_manager(scripted)
    state.add_user_message("这个太难了，我不想学了。")
    d = manager.decide(state)
    assert (d.speaker, d.function) == ("assistant", "encourage")
    assert any("不想学" in m["content"]
               for call in scripted.calls for m in call)


def test_manager_handles_offtopic_user():  # Test 8
    scripted = ScriptedLLM([decision_json("class_clown", "redirect",
                                          "用户跑题")])
    manager, state = make_manager(scripted)
    state.add_user_message("我想聊点别的，最近在玩原神。")
    d = manager.decide(state)
    assert (d.speaker, d.function) == ("class_clown", "redirect")


def test_manager_invalid_json_retries_then_valid():
    scripted = ScriptedLLM(["这不是 JSON", decision_json("teacher", "teach")])
    manager, state = make_manager(scripted)
    d = manager.decide(state)
    assert (d.speaker, d.function) == ("teacher", "teach")
    assert len(scripted.calls) == 2  # retry 发生过


def test_manager_invalid_json_falls_back_without_crash():
    scripted = ScriptedLLM(["garbage", "still not json", "{bad}"])
    manager, state = make_manager(scripted)
    d = manager.decide(state)
    assert d.speaker == "teacher"  # fallback 不崩溃
    assert d.function in ("teach", "answer_question", "next_material", "summarize")


def test_manager_rejects_permission_violation():
    # teacher -> ask_question 不在 teacher 权限内 -> retry 后 fallback
    scripted = ScriptedLLM([decision_json("teacher", "ask_question")] * 3)
    manager, state = make_manager(scripted)
    d = manager.decide(state)
    assert d.function != "ask_question"


def test_manager_json_in_code_fence():
    fenced = "```json\n" + decision_json("teacher", "teach") + "\n```"
    scripted = ScriptedLLM([fenced])
    manager, state = make_manager(scripted)
    d = manager.decide(state)
    assert (d.speaker, d.function) == ("teacher", "teach")


def test_manager_brief_contains_state():
    scripted = ScriptedLLM([decision_json("teacher", "teach")])
    manager, state = make_manager(scripted)
    state.mark_taught()
    state.add_entry_user = None
    manager.decide(state)
    brief = scripted.calls[0][1]["content"]
    assert "当前材料" in brief
    assert "所有材料已完成: no" in brief
    assert "剩余材料" in brief
