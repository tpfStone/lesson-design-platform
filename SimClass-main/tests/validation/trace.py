"""决策轨迹工具: 紧凑文本输出 + 结构化 JSON 报告（保存到 logs/validation/）。

复用 runner 记录的 trace 与 SessionLogger 的落盘习惯，不另建日志系统。
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from .criteria import Verdict
from .runner import ScenarioResult


def compact_trace(records: list[dict]) -> str:
    """人类可读的紧凑轨迹:
        Turn 1
        Material: What is an LLM?
        Decision: teacher → teach
    """
    blocks = []
    for r in records:
        blocks.append(
            f"Turn {r['turn_id']}\n"
            f"Material: {r['current_material_before']}\n"
            f"Decision: {r['speaker']} → {r['function']}"
        )
    return "\n\n".join(blocks)


def save_validation_report(scenario: str, user_message: str | None,
                           result: ScenarioResult, verdict: Verdict,
                           out_dir: str = "logs/validation") -> str:
    """保存结构化验证报告，返回文件路径。"""
    os.makedirs(out_dir, exist_ok=True)
    payload = {
        "scenario": scenario,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "user_message": user_message,
        "verdict": {
            "passed": verdict.passed,
            "passes": verdict.passes,
            "failures": verdict.failures,
        },
        "crashed": result.crashed,
        "error": result.error,
        "continuation_ok": result.continuation_ok,
        "final_status": result.final_status,
        "trace": result.records,
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"{scenario}_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def print_report(title: str, user_message: str | None,
                 result: ScenarioResult, verdict: Verdict,
                 json_path: str | None = None) -> None:
    """真实 LLM 冒烟测试的终端输出格式。"""
    print("\n" + "=" * 50)
    print(f"SCENARIO: {title}")
    print("=" * 50)
    if user_message:
        print("\nUser:")
        print(user_message)
    print()
    print(compact_trace(result.records))
    print(f"\nResult: {'PASS' if verdict.passed else 'FAIL'}")
    for msg in verdict.passes:
        print(f"  + {msg}")
    for msg in verdict.failures:
        print(f"  - {msg}")
    if json_path:
        print(f"\nSaved: {json_path}")
