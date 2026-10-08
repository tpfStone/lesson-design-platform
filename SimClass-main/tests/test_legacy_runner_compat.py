from app.classroom import classroom_v2  # noqa: F401 - installs the legacy step method
from app.classroom.classroom import Classroom
from app.llm.mock import MockProvider


def test_legacy_step_adapter_now_returns_dialogue_entry(tmp_path):
    classroom = Classroom(llm=MockProvider(), log_dir=str(tmp_path))
    entry = classroom.step("什么是一次函数？")
    assert entry is not None
    assert entry.speaker == "assistant"
    assert entry.function == "answer_question"
    assert classroom.state.dialogue_history[-1] is entry
