"""Test 2 / 3 / 9 / 10 相关: Agent + FunctionExecutor。"""
import pytest

from app.agents import AGENT_CLASSES
from app.controller.executor import FunctionExecutor, InvalidActionError
from app.controller.state import ClassState, ManagerDecision
from app.llm.mock import MockProvider
from app.materials import load_materials


def make_executor_and_state():
    llm = MockProvider()
    agents = {cls.name: cls(llm) for cls in AGENT_CLASSES}
    state = ClassState(load_materials(), list(agents.keys()))
    return FunctionExecutor(agents), agents, state


def test_classroom_agents_registered():
    _, agents, _ = make_executor_and_state()
    assert set(agents) == {"teacher", "assistant", "class_clown",
                           "deep_thinker", "note_taker", "inquisitive_mind"}


def test_teacher_can_teach():  # Test 2
    executor, _, state = make_executor_and_state()
    entry = executor.execute(ManagerDecision("teacher", "teach", "test"), state)
    assert entry.speaker == "teacher" and entry.function == "teach"
    assert entry.content  # 有实际发言内容
    assert state.taught_materials == ["What is an LLM?"]
    assert state.last_speaker == "teacher"
    assert state.last_function == "teach"


def test_user_question_then_assistant_answers():  # Test 3（用户提问进入流程）
    executor, _, state = make_executor_and_state()
    state.add_user_message("Transformer 为什么比 RNN 更适合处理长距离依赖？")
    entry = executor.execute(
        ManagerDecision("assistant", "answer_question", "test"), state)
    assert entry.speaker == "assistant"
    assert state.dialogue_history[-2].speaker == "user"  # 用户发言在历史中


def test_teacher_next_material():  # Test 9
    executor, _, state = make_executor_and_state()
    first = state.current_material["title"]
    executor.execute(ManagerDecision("teacher", "teach"), state)
    executor.execute(ManagerDecision("teacher", "next_material"), state)
    assert state.current_material["title"] != first
    assert first in state.taught_materials


def test_full_course_progress():  # Test 10（状态层面讲完全部材料）
    executor, _, state = make_executor_and_state()
    for _ in range(5):
        executor.execute(ManagerDecision("teacher", "teach"), state)
        executor.execute(ManagerDecision("teacher", "next_material"), state)
    assert state.all_materials_finished
    assert state.current_material is None


def test_permission_denied_for_classmate_teach():  # Test 25 权限校验
    executor, _, state = make_executor_and_state()
    with pytest.raises(InvalidActionError):
        executor.execute(ManagerDecision("note_taker", "teach"), state)
    with pytest.raises(InvalidActionError):
        executor.execute(ManagerDecision("assistant", "next_material"), state)


def test_teach_forbidden_after_all_materials():
    executor, _, state = make_executor_and_state()
    for _ in range(5):
        state.advance_material()
    with pytest.raises(InvalidActionError):
        executor.execute(ManagerDecision("teacher", "teach"), state)


def test_interaction_functions_run():
    executor, agents, state = make_executor_and_state()
    cases = [
        ("teacher", "elaborate"), ("assistant", "encourage"),
        ("class_clown", "redirect"), ("deep_thinker", "ask_question"),
        ("note_taker", "summarize"), ("inquisitive_mind", "discuss"),
    ]
    for speaker, function in cases:
        entry = executor.execute(ManagerDecision(speaker, function, "test"), state)
        assert entry.content
    assert len(state.dialogue_history) == len(cases)
