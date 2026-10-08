from app.classroom.classroom import Classroom
from app.classroom.events import ClassroomEvent, TRIGGER_INITIALIZATION, TRIGGER_TIMEOUT
from app.llm.base import LLMError
from app.llm.mock import MockProvider


def test_agent_llm_error_does_not_kill_classroom_and_clears_pending(tmp_path):
    classroom = Classroom(llm=MockProvider(), log_dir=str(tmp_path))
    original_execute = classroom.executor.execute
    calls = {"count": 0}

    def flaky_execute(decision, state):
        calls["count"] += 1
        if calls["count"] == 1:
            raise LLMError("temporary provider failure")
        return original_execute(decision, state)

    classroom.executor.execute = flaky_execute
    classroom._process_event(ClassroomEvent(TRIGGER_INITIALIZATION))
    assert classroom._run_one_turn() is None
    assert classroom.state.pending_user_message is None
    assert classroom.last_turn_error.startswith("agent_llm_error")
    assert classroom.state.session_status == "active"

    classroom._process_event(ClassroomEvent(TRIGGER_TIMEOUT))
    entry = classroom._run_one_turn()
    assert entry is not None
    assert classroom.state.session_status == "active"


def test_manager_llm_error_skips_turn_and_next_turn_continues(tmp_path):
    classroom = Classroom(llm=MockProvider(), log_dir=str(tmp_path))
    original_decide = classroom.manager.decide
    calls = {"count": 0}

    def flaky_decide(state, feedback=None):
        calls["count"] += 1
        if calls["count"] == 1:
            raise LLMError("manager timeout")
        return original_decide(state, feedback=feedback)

    classroom.manager.decide = flaky_decide
    classroom._process_event(ClassroomEvent(TRIGGER_INITIALIZATION))
    assert classroom._run_one_turn() is None
    assert classroom.state.pending_user_message is None
    assert classroom.state.session_status == "active"

    classroom._process_event(ClassroomEvent(TRIGGER_TIMEOUT))
    assert classroom._run_one_turn() is not None
    assert classroom.state.session_status == "active"
