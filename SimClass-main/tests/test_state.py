"""Test 1 / 9 / 10 相关: ClassState 基础行为。"""
from app.controller.state import ClassState
from app.materials import load_materials

ROLES = ["teacher", "assistant", "class_clown", "deep_thinker",
         "note_taker", "inquisitive_mind"]


def make_state():
    return ClassState(load_materials(), ROLES)


def test_initial_state():
    state = make_state()
    assert state.session_status == "active"
    assert state.current_material["id"] == 1
    assert state.taught_materials == []
    assert state.dialogue_history == []
    assert state.last_speaker is None
    assert set(ROLES) == set(state.class_roles)


def test_remaining_materials():
    state = make_state()
    assert len(state.remaining_materials) == 5
    assert state.all_materials_finished is False


def test_mark_taught_and_advance():
    state = make_state()
    state.mark_taught()
    assert state.current_material_taught is True
    state.advance_material()
    assert state.current_material["id"] == 2
    assert state.taught_materials == ["What is an LLM?"]


def test_all_materials_finished():
    state = make_state()
    for _ in range(5):
        state.advance_material()
    assert state.current_material is None
    assert state.all_materials_finished is True
    assert len(state.taught_materials) == 5


def test_user_message_enters_history():
    state = make_state()
    state.add_user_message("什么是 tokenization？")
    assert state.dialogue_history[-1].speaker == "user"
    assert state.pending_user_message == "什么是 tokenization？"
    assert state.last_speaker == "user"
