r"""B 类验证: 真实 LLM 冒烟测试 —— 仅在 RUN_REAL_LLM_TESTS=true 时运行。

默认关闭（消耗 API token 且结果非确定性），普通 pytest 不受影响。

运行方式:
    PowerShell:  $env:RUN_REAL_LLM_TESTS="true"; .venv\Scripts\python -m pytest tests/test_validation_real.py -v -s
    bash:        RUN_REAL_LLM_TESTS=true python -m pytest tests/test_validation_real.py -v -s

每次运行把完整决策轨迹与 PASS/FAIL 判定保存到
logs/validation/<scenario>_<TIMESTAMP>.json。
"""
import os

import pytest

from app.classroom.classroom import Classroom
from app.llm.provider import create_llm
from tests.validation.criteria import (
    evaluate_negative_emotion,
    evaluate_off_topic,
    evaluate_progression,
)
from tests.validation.runner import run_scenario
from tests.validation.trace import print_report, save_validation_report

RUN_REAL = os.getenv("RUN_REAL_LLM_TESTS", "").strip().lower() == "true"
pytestmark = pytest.mark.skipif(
    not RUN_REAL,
    reason="需要 RUN_REAL_LLM_TESTS=true（真实 LLM 冒烟测试，消耗 token，默认关闭）",
)

NEGATIVE_MSG = "这个太难了，我完全听不懂，也不想继续学了。"
OFFTOPIC_MSG = "先别讲 LLM 了，我们聊聊最近有什么好玩的游戏吧。"

EVALUATORS = {
    "negative_emotion": evaluate_negative_emotion,
    "off_topic": evaluate_off_topic,
    "progression": evaluate_progression,
}


def _make_classroom() -> Classroom:
    return Classroom(llm=create_llm(), input_fn=lambda *a: "")


def _run(title: str, scenario: str, user_message: str | None, max_turns: int,
         pace_seconds: float = 4.0) -> None:
    result = run_scenario(_make_classroom(),
                          user_message=user_message, max_turns=max_turns,
                          pace_seconds=pace_seconds)  # 免费档限流防护
    verdict = EVALUATORS[scenario](result)
    path = save_validation_report(scenario, user_message, result, verdict)
    print_report(title, user_message, result, verdict, json_path=path)

    assert not result.crashed, f"Runner crashed: {result.error}"
    assert verdict.passed, "FAIL:\n" + "\n".join(verdict.failures)


def test_real_negative_emotion():
    _run("Negative Emotion", "negative_emotion", NEGATIVE_MSG, max_turns=6)


def test_real_off_topic():
    _run("Off-topic", "off_topic", OFFTOPIC_MSG, max_turns=6)


def test_real_progression():
    _run("Continuous Progression", "progression", None, max_turns=30,
         pace_seconds=20.0)  # 长场景: 更慢的节奏以适配免费档 TPM 配额
