"""显式 PASS / FAIL 行为判据。

原则（对应任务第 1/8 节）:
- 只验证行为约束，不断言具体 speaker（Manager 是 LLM-powered，非确定性）。
- 可疑行为不得静默视为 PASS，失败必须给出准确原因。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .runner import ScenarioResult

SUPPORTIVE_FUNCTIONS = {"encourage"}
# 重定向后代表"回到学习流程"的动作
RESUME_FUNCTIONS = {"teach", "next_material", "elaborate", "answer_question", "summarize"}
VALID_STATUSES = {"active", "waiting", "finished"}


@dataclass
class Verdict:
    passed: bool = True
    passes: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def ok(self, msg: str) -> None:
        self.passes.append(msg)

    def fail(self, msg: str) -> None:
        self.failures.append(msg)
        self.passed = False


def _check_common(result: ScenarioResult, v: Verdict) -> None:
    """所有场景共用的基础判据: 不崩溃 / 决策合法 / 状态有效。"""
    if result.crashed:
        v.fail(f"Runner crashed: {result.error}")
    else:
        v.ok("No crash occurred during the scenario loop.")

    bad = [r for r in result.records if r["validation_status"] != "ok"]
    if bad:
        turns = ", ".join(str(r["turn_id"]) for r in bad)
        v.fail(f"Invalid speaker/function decision at turn(s) {turns}: {bad[0]['validation_status']}")
    else:
        v.ok("All speaker/function combinations passed permission validation.")

    if result.final_status in VALID_STATUSES:
        v.ok(f"session_status remained valid (final: {result.final_status}).")
    else:
        v.fail(f"Invalid session_status: {result.final_status}")


def evaluate_negative_emotion(result: ScenarioResult, window: int | None = None) -> Verdict:
    """负面情绪场景: 出现支持性行为 / 不崩溃 / 状态有效 / 之后可继续。"""
    v = Verdict()
    _check_common(result, v)

    records = result.records[:window] if window else result.records
    supportive = [r for r in records if r["function"] in SUPPORTIVE_FUNCTIONS]
    if supportive:
        r = supportive[0]
        v.ok(f"Supportive behavior occurred: {r['speaker']} → {r['function']} "
             f"at turn {r['turn_id']}.")
    else:
        v.fail(f"No supportive action ({'/'.join(sorted(SUPPORTIVE_FUNCTIONS))}) "
               f"detected within {len(records)} turns.")

    if result.finished:
        v.ok("Classroom finished the course afterwards.")
    elif result.continuation_ok is False:
        v.fail("Classroom could not continue after the scenario.")
    else:
        v.ok("Classroom can continue the lesson afterwards (continuation turn executed).")
    return v


def evaluate_off_topic(result: ScenarioResult) -> Verdict:
    """跑题场景: 出现 redirect / redirect 当轮不跳过材料 / 之后回到学习流程。"""
    v = Verdict()
    _check_common(result, v)

    redirects = [r for r in result.records if r["function"] == "redirect"]
    if not redirects:
        v.fail(f"No redirect action detected within {len(result.records)} turns.")
        return v

    r = redirects[0]
    v.ok(f"Redirection occurred: {r['speaker']} → redirect at turn {r['turn_id']}.")

    if r["current_material_after"] != r["current_material_before"]:
        v.fail(f"Current material was skipped during redirect "
               f"({r['current_material_before']} → {r['current_material_after']}).")
    else:
        v.ok("Current material was not skipped during redirect.")

    after = result.records[r["turn_id"]:]  # redirect 轮之后的所有记录
    resumed = (any(x["function"] in RESUME_FUNCTIONS for x in after)
               or result.continuation_ok or result.finished)
    if resumed:
        v.ok("Classroom returned to the learning flow after the redirect.")
    else:
        v.fail("Classroom remained off-topic: no learning-flow action after redirect.")
    return v


def evaluate_progression(result: ScenarioResult,
                         max_repeat: int = 3, min_transitions: int = 1) -> Verdict:
    """连续推进场景: 不崩溃 / 决策合法 / 无明显无限重复 / 材料有推进。"""
    v = Verdict()
    _check_common(result, v)

    # 连续相同决策检测（speaker + function 完全一致）
    best_streak, best_key, cur, cur_key = 0, None, 0, None
    for r in result.records:
        key = (r["speaker"], r["function"])
        if key == cur_key:
            cur += 1
        else:
            cur, cur_key = 1, key
        if cur > best_streak:
            best_streak, best_key = cur, key
    if best_streak > max_repeat:
        v.fail(f"The same decision {best_key[0]} → {best_key[1]} "
               f"repeated {best_streak} times consecutively.")
    else:
        v.ok(f"No obvious infinite repetition "
             f"(max consecutive identical decision: {best_streak}).")

    # 材料推进检测
    transitions = [r for r in result.records
                   if r["current_material_before"] != r["current_material_after"]]
    if len(transitions) >= min_transitions:
        names = " → ".join(dict.fromkeys(
            t["current_material_after"] for t in transitions if t["current_material_after"]))
        v.ok(f"Material transitions occurred: {len(transitions)} ({names}).")
    else:
        v.fail(f"No material transition occurred within {len(result.records)} turns.")
    return v
