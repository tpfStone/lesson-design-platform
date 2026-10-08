"""Test 1 / 3 / 4 / 7 / 8 / 10 相关: 端到端 Classroom Loop（MockProvider）。"""
import json
import os

from app.classroom.classroom import Classroom
from app.llm.mock import MockProvider


def make_classroom(inputs, tmp_path):
    seq = iter(inputs)

    def input_fn(_prompt=""):
        return next(seq, "quit")  # 输入耗尽后自动 quit

    return Classroom(llm=MockProvider(), input_fn=input_fn, log_dir=str(tmp_path))


def test_classroom_starts_and_teaches(tmp_path, capsys):  # Test 1 + 2
    classroom = make_classroom(["", ""], tmp_path)
    classroom.run()
    out = capsys.readouterr().out
    assert "SimClass MVP" in out
    assert classroom.state.session_status == "finished"
    assert classroom.state.dialogue_history[0].speaker == "teacher"
    assert classroom.state.dialogue_history[0].function == "teach"


def test_user_question_flow(tmp_path):  # Test 3 + 4
    classroom = make_classroom(
        ["", "Transformer 和 RNN 有什么区别？", ""], tmp_path)
    classroom.run()
    history = classroom.state.dialogue_history
    speakers = [e.speaker for e in history]
    functions = [e.function for e in history]
    assert "user" in speakers           # 用户发言进入历史
    assert "answer_question" in functions  # 有人回答了用户问题
    answer = next(e for e in history if e.function == "answer_question")
    assert answer.speaker == "assistant"  # Manager 选了 assistant


def test_negative_emotion_gets_encouragement(tmp_path):  # Test 7
    classroom = make_classroom(["", "这个太难了，我不想学了。", ""], tmp_path)
    classroom.run()
    functions = [e.function for e in classroom.state.dialogue_history]
    assert "encourage" in functions
    entry = next(e for e in classroom.state.dialogue_history
                 if e.function == "encourage")
    assert entry.speaker in ("assistant", "class_clown", "inquisitive_mind")


def test_offtopic_user_gets_redirect(tmp_path):  # Test 8
    classroom = make_classroom(["", "我想聊点别的，最近在玩原神", ""], tmp_path)
    classroom.run()
    functions = [e.function for e in classroom.state.dialogue_history]
    assert "redirect" in functions


def test_full_course_runs_to_end(tmp_path):  # Test 9 + 10
    classroom = make_classroom([""] * 30, tmp_path)
    classroom.run()
    assert classroom.state.session_status == "finished"
    assert classroom.state.all_materials_finished
    assert len(classroom.state.taught_materials) == 5
    functions = [e.function for e in classroom.state.dialogue_history]
    assert functions.count("teach") == 5
    assert functions.count("next_material") == 5
    assert "summarize" in functions  # 最终总结出现过


def test_session_log_saved(tmp_path):  # Logging
    classroom = make_classroom(["", ""], tmp_path)
    classroom.run()
    log_files = os.listdir(tmp_path)
    assert len(log_files) == 1 and log_files[0].startswith("session_")
    with open(os.path.join(tmp_path, log_files[0]), encoding="utf-8") as f:
        records = json.load(f)
    assert records
    for r in records:
        assert {"timestamp", "speaker", "function", "reason",
                "user_message", "response"} <= set(r)


def test_quit_command_ends_class(tmp_path):
    classroom = make_classroom(["", "quit"], tmp_path)
    classroom.run()
    assert classroom.state.session_status == "finished"
