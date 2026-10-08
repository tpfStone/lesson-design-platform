"""
F3 simplified demo runner.

Assumptions:
- F4 and F3 HTTP services are already running.
- F4 -> F3 identity contract is the hardened baseline.
- This runner never starts F4/F3 services and never hides Mock model output.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from run_f4_to_f3_auto import (
    build_f3_materials,
    get_f3_state,
    get_f4_current_state,
    send_f3_message,
    start_f3_classroom,
    verify_f3_mapping,
    write_json_atomic,
)

DEFAULT_TIMEOUT = 30


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _require_nonempty_string(data: Dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"配置字段 {key} 必须为非空字符串")
    return value.strip()


def load_config(path: str | Path) -> Dict[str, Any]:
    config_path = Path(path)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"配置文件不存在: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"配置文件不是有效 JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("配置文件顶层必须是 JSON 对象")

    normalized: Dict[str, Any] = {
        "f4Url": _require_nonempty_string(data, "f4Url"),
        "f3Url": _require_nonempty_string(data, "f3Url"),
        "lessonId": _require_nonempty_string(data, "lessonId"),
        "versionId": _require_nonempty_string(data, "versionId"),
        "f4SessionId": _require_nonempty_string(data, "f4SessionId"),
        "rounds": data.get("rounds", 4),
        "messages": data.get("messages"),
        "outputDir": data.get("outputDir", "outputs/f3_demo"),
        "f2Url": data.get("f2Url", "http://127.0.0.1:8080"),
        "writebackToF2": data.get("writebackToF2", False),
    }

    rounds = normalized["rounds"]
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 10:
        raise ValueError("rounds 必须是 1–10 之间的整数")

    messages = normalized["messages"]
    if not isinstance(messages, list):
        raise ValueError("messages 必须是数组")
    if len(messages) < rounds:
        raise ValueError("messages 数量不得少于 rounds")
    if any(not isinstance(message, str) or not message.strip() for message in messages):
        raise ValueError("messages 中每一项都必须是非空字符串")
    normalized["messages"] = [message.strip() for message in messages]

    output_dir = normalized["outputDir"]
    if not isinstance(output_dir, str) or not output_dir.strip():
        raise ValueError("outputDir 必须为非空字符串")
    normalized["outputDir"] = output_dir.strip()

    f2_url = normalized["f2Url"]
    if not isinstance(f2_url, str) or not f2_url.strip():
        raise ValueError("f2Url 必须为非空字符串")
    normalized["f2Url"] = f2_url.strip()

    writeback = normalized["writebackToF2"]
    if not isinstance(writeback, bool):
        raise ValueError("writebackToF2 必须是 true/false")
    return normalized


def check_f4_service(session: requests.Session, f4_url: str) -> None:
    url = f"{f4_url.rstrip('/')}/api/health"
    try:
        response = session.get(url, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"无法访问 F4 服务，请检查 8000/F4 地址: {exc}") from exc
    if response.status_code == 404:
        # 允许旧 F4 没有健康检查；随后 current-state 会完成真实可用性验证。
        return
    if not response.ok:
        raise RuntimeError(f"F4 健康检查失败: HTTP {response.status_code}")


def check_f3_service(session: requests.Session, f3_url: str) -> None:
    url = f"{f3_url.rstrip('/')}/health"
    try:
        response = session.get(url, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"无法访问 F3 服务，请检查 8003/F3 地址: {exc}") from exc
    if not response.ok:
        raise RuntimeError(f"F3 健康检查失败: HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("F3 /health 返回不是有效 JSON") from exc
    if not isinstance(data, dict) or data.get("status") != "up":
        raise RuntimeError("F3 /health 未返回 status=up")


def _expected_source(f4_session_id: str, f4_lesson_plan_id: str) -> Dict[str, str]:
    return {
        "module": "F4",
        "session_id": f4_session_id,
        "lesson_plan_id": f4_lesson_plan_id,
    }


def verify_start_mapping(
    start_data: Dict[str, Any],
    lesson_id: str,
    version_id: str,
    f4_session_id: str,
    f4_lesson_plan_id: str,
) -> None:
    if start_data.get("lesson_id") != lesson_id:
        raise ValueError("F3 /start lesson_id 与 F2 lessonId 不一致")
    if start_data.get("version_id") != version_id:
        raise ValueError("F3 /start version_id 与 F2 versionId 不一致")
    if start_data.get("source") != _expected_source(f4_session_id, f4_lesson_plan_id):
        raise ValueError("F3 /start source 身份映射不一致")
    if not start_data.get("session_id"):
        raise ValueError("F3 /start 未返回 session_id")


def _f4_provider(f4_state: Dict[str, Any]) -> str:
    snapshot = (f4_state.get("session") or {}).get("config_snapshot")
    if isinstance(snapshot, dict):
        provider = snapshot.get("provider")
        if provider:
            return str(provider)
    return "UNKNOWN"


def _f3_model_mode(round_records: List[Dict[str, Any]]) -> str:
    if not round_records:
        return "NOT_TESTED"
    contents = [str((item.get("response") or {}).get("content", "")) for item in round_records]
    if any("[MockLLM]" in content for content in contents):
        return "MOCK"
    return "UNVERIFIED"


def _resolve_output_base(output_dir: str) -> Path:
    path = Path(output_dir)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parent / path


def create_run_dir(output_dir: str, f3_session_id: str, when: Optional[datetime] = None) -> Path:
    base = _resolve_output_base(output_dir)
    base.mkdir(parents=True, exist_ok=True)
    moment = when or datetime.now().astimezone()
    stem = f"{moment.strftime('%Y%m%d_%H%M%S')}_{f3_session_id[:8]}"
    candidate = base / stem
    suffix = 2
    while candidate.exists():
        candidate = base / f"{stem}_{suffix}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def write_text_atomic(path: Path, text: str) -> None:
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def build_session_record(
    *,
    status: str,
    started_at: str,
    finished_at: str,
    lesson_id: str,
    version_id: str,
    f4_session_id: str,
    f4_lesson_plan_id: str,
    f3_session_id: str,
    requested_rounds: int,
    round_records: List[Dict[str, Any]],
    materials: List[Dict[str, Any]],
    final_state: Dict[str, Any],
    f4_state: Dict[str, Any],
    error: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "status": status,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "lessonId": lesson_id,
        "versionId": version_id,
        "f4SessionId": f4_session_id,
        "f4LessonPlanId": f4_lesson_plan_id,
        "f3SessionId": f3_session_id,
        "requestedRounds": requested_rounds,
        "completedRounds": len(round_records),
        "materialCount": len(materials),
        "materials": materials,
        "rounds": round_records,
        "finalState": final_state,
        "executionBoundary": {
            "httpChain": "REAL",
            "f4Provider": _f4_provider(f4_state),
            "f3ModelContent": _f3_model_mode(round_records),
            "note": (
                "F4/F3 HTTP calls and state transitions are live when this record is "
                "produced by run_f3_demo.py. Model content may still be Mock."
            ),
        },
    }
    if error is not None:
        result["error"] = error
    return result


def build_summary(record: Dict[str, Any]) -> str:
    lines: List[str] = [
        "# F3 课堂模拟简报",
        "",
        f"- 运行状态：**{record['status']}**",
        f"- 开始时间：{record['startedAt']}",
        f"- 结束时间：{record['finishedAt']}",
        f"- F2 lessonId：`{record['lessonId']}`",
        f"- F2 versionId：`{record['versionId']}`",
        f"- F4 session.id：`{record['f4SessionId']}`",
        f"- F4 lesson_plan.id：`{record['f4LessonPlanId']}`",
        f"- F3 session_id：`{record['f3SessionId']}`",
        f"- 课堂材料数：{record['materialCount']}",
        f"- 计划轮数：{record['requestedRounds']}",
        f"- 完成轮数：{record['completedRounds']}",
        f"- 最终状态：{(record.get('finalState') or {}).get('status', 'UNKNOWN')}",
        f"- 最终 history 条目数：{len((record.get('finalState') or {}).get('history', []))}",
        "",
        "## 课堂材料",
        "",
    ]
    for material in record.get("materials", []):
        metadata = material.get("metadata") or {}
        lines.append(
            f"- {material.get('id')}. {material.get('title')} "
            f"(`{metadata.get('source_section_type', 'unknown')}`, "
            f"sourceSectionId=`{metadata.get('source_section_id', '')}`)"
        )

    lines.extend(["", "## 各轮记录", ""])
    for item in record.get("rounds", []):
        response = item.get("response") or {}
        lines.extend(
            [
                f"### 第 {item.get('round')} 轮",
                "",
                f"- 输入：{item.get('input', '')}",
                f"- 发言角色：`{response.get('speaker', '')}`",
                f"- 动作类型：`{response.get('function', '')}`",
                f"- 回复：{response.get('content', '')}",
                f"- 本轮结束状态：`{item.get('stateStatus', '')}`",
                f"- 本轮 history 条目数：{item.get('historyCount', 0)}",
                "",
            ]
        )

    boundary = record.get("executionBoundary") or {}
    lines.extend(
        [
            "## REAL / MOCK 边界",
            "",
            f"- HTTP 链路：`{boundary.get('httpChain', 'UNKNOWN')}`",
            f"- F4 Provider：`{boundary.get('f4Provider', 'UNKNOWN')}`",
            f"- F3 模型内容：`{boundary.get('f3ModelContent', 'UNKNOWN')}`",
            "",
            "> HTTP、F4 current-state、F3 session 创建与状态查询属于真实调用；若模型 Provider 或回复标记为 Mock，则模型生成文本不代表正式模型效果。",
        ]
    )

    if record.get("status") == "FAILED":
        error = record.get("error") or {}
        lines.extend(
            [
                "",
                "## 失败信息",
                "",
                f"- 失败轮次：{error.get('round', '未进入课堂轮次')}",
                f"- 异常类型：`{error.get('type', 'Unknown')}`",
                f"- 异常信息：{error.get('message', '')}",
            ]
        )

    return "\n".join(lines) + "\n"


def run_demo(
    config: Dict[str, Any],
    *,
    http_session: Optional[requests.Session] = None,
    rounds_override: Optional[int] = None,
    output_dir_override: Optional[str] = None,
) -> Dict[str, Any]:
    config = dict(config)
    if rounds_override is not None:
        if isinstance(rounds_override, bool) or not 1 <= rounds_override <= 10:
            raise ValueError("--rounds 必须在 1–10 之间")
        config["rounds"] = rounds_override
        if len(config["messages"]) < rounds_override:
            raise ValueError("messages 数量不得少于覆盖后的 rounds")
    if output_dir_override is not None:
        if not output_dir_override.strip():
            raise ValueError("--output-dir 不得为空")
        config["outputDir"] = output_dir_override.strip()

    session = http_session or requests.Session()
    started_at = _now_iso()
    check_f4_service(session, config["f4Url"])
    check_f3_service(session, config["f3Url"])

    f4_state = get_f4_current_state(
        config["f4Url"], config["f4SessionId"], http_session=session
    )
    f4_lesson_plan_id = str(f4_state["lesson_plan"]["id"])
    materials = build_f3_materials(f4_state)

    start_data = start_f3_classroom(
        config["f3Url"],
        config["lessonId"],
        config["versionId"],
        config["f4SessionId"],
        f4_lesson_plan_id,
        materials,
        http_session=session,
    )
    verify_start_mapping(
        start_data,
        config["lessonId"],
        config["versionId"],
        config["f4SessionId"],
        f4_lesson_plan_id,
    )
    f3_session_id = str(start_data["session_id"])
    run_dir = create_run_dir(config["outputDir"], f3_session_id)
    record_path = run_dir / "session_record.json"
    summary_path = run_dir / "summary.md"

    round_records: List[Dict[str, Any]] = []
    last_state: Dict[str, Any] = {}
    failure: Optional[Dict[str, Any]] = None

    try:
        for index in range(config["rounds"]):
            round_number = index + 1
            message = config["messages"][index]
            response = send_f3_message(
                config["f3Url"], f3_session_id, message, http_session=session
            )
            state = get_f3_state(
                config["f3Url"], f3_session_id, http_session=session
            )
            verify_f3_mapping(
                start_data,
                state,
                config["lessonId"],
                config["versionId"],
                config["f4SessionId"],
                f4_lesson_plan_id,
            )
            last_state = state
            round_records.append(
                {
                    "round": round_number,
                    "input": message,
                    "response": response,
                    "stateStatus": state.get("status"),
                    "historyCount": len(state.get("history") or []),
                    "stateSnapshot": state,
                }
            )

        final_state = get_f3_state(
            config["f3Url"], f3_session_id, http_session=session
        )
        verify_f3_mapping(
            start_data,
            final_state,
            config["lessonId"],
            config["versionId"],
            config["f4SessionId"],
            f4_lesson_plan_id,
        )
        last_state = final_state
        status = "COMPLETED"
    except Exception as exc:
        status = "FAILED"
        failure = {
            "round": min(len(round_records) + 1, config["rounds"]),
            "type": type(exc).__name__,
            "message": str(exc),
        }

    record = build_session_record(
        status=status,
        started_at=started_at,
        finished_at=_now_iso(),
        lesson_id=config["lessonId"],
        version_id=config["versionId"],
        f4_session_id=config["f4SessionId"],
        f4_lesson_plan_id=f4_lesson_plan_id,
        f3_session_id=f3_session_id,
        requested_rounds=config["rounds"],
        round_records=round_records,
        materials=materials,
        final_state=last_state,
        f4_state=f4_state,
        error=failure,
    )
    write_json_atomic(record_path, record)
    write_text_atomic(summary_path, build_summary(record))

    record["sessionRecordPath"] = str(record_path.resolve())
    record["summaryPath"] = str(summary_path.resolve())
    return record



def _load_local_artifacts(run_dir: str | Path) -> tuple[Path, Path, Dict[str, Any], str]:
    directory = Path(run_dir)
    record_path = directory / "session_record.json"
    summary_path = directory / "summary.md"
    if not record_path.is_file():
        raise ValueError(f"找不到 session_record.json: {record_path}")
    if not summary_path.is_file():
        raise ValueError(f"找不到 summary.md: {summary_path}")
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"session_record.json 不是有效 JSON: {exc}") from exc
    if not isinstance(record, dict):
        raise ValueError("session_record.json 顶层必须是 JSON 对象")
    summary = summary_path.read_text(encoding="utf-8")
    if not summary.strip():
        raise ValueError("summary.md 不能为空")
    return record_path, summary_path, record, summary


def writeback_to_f2(
    config: Dict[str, Any],
    run_dir: str | Path,
    *,
    http_session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """将已完成的本地 F3 结果通过 F2 HTTP API 持久化，并单独写回执。"""
    session = http_session or requests.Session()
    record_path, summary_path, record, summary = _load_local_artifacts(run_dir)
    if record.get("status") != "COMPLETED":
        raise RuntimeError("只有 COMPLETED 的课堂模拟结果才能回写 F2")

    lesson_id = str(record.get("lessonId") or "").strip()
    version_id = str(record.get("versionId") or "").strip()
    f3_session_id = str(record.get("f3SessionId") or "").strip()
    if not lesson_id or not version_id or not f3_session_id:
        raise ValueError("本地结果缺少 lessonId/versionId/f3SessionId")

    # 正常模式下配置与本地结果必须属于同一教案版本；显式 retry 也沿用此保护。
    if config.get("lessonId") and config["lessonId"] != lesson_id:
        raise ValueError("配置 lessonId 与本地结果不一致")
    if config.get("versionId") and config["versionId"] != version_id:
        raise ValueError("配置 versionId 与本地结果不一致")

    url = f"{config['f2Url'].rstrip('/')}/api/platform/lessons/{lesson_id}/simulations"
    payload = {"sessionRecord": record, "summaryMarkdown": summary}
    try:
        response = session.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"模拟已完成、F2 保存失败，可重试回写: {exc}") from exc

    if response.status_code not in (200, 201):
        detail = response.text[:1000] if getattr(response, "text", None) else ""
        raise RuntimeError(
            f"模拟已完成、F2 保存失败，可重试回写: HTTP {response.status_code} {detail}"
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("模拟已完成、F2 保存失败，可重试回写: F2 返回非 JSON") from exc
    if not isinstance(data, dict) or not data.get("simulationRunId"):
        raise RuntimeError("模拟已完成、F2 保存失败，可重试回写: F2 未返回 simulationRunId")
    if data.get("lessonId") != lesson_id or data.get("versionId") != version_id:
        raise RuntimeError("模拟已完成、F2 保存失败，可重试回写: F2 返回身份映射不一致")
    if data.get("f3SessionId") != f3_session_id:
        raise RuntimeError("模拟已完成、F2 保存失败，可重试回写: F2 返回 f3SessionId 不一致")

    receipt = {
        "simulationRunId": data["simulationRunId"],
        "lessonId": lesson_id,
        "versionId": version_id,
        "f3SessionId": f3_session_id,
        "alreadySaved": bool(data.get("alreadySaved", False)),
        "writtenBackAt": _now_iso(),
    }
    receipt_path = Path(run_dir) / "f2_writeback_receipt.json"
    write_json_atomic(receipt_path, receipt)
    receipt["receiptPath"] = str(receipt_path.resolve())
    receipt["sessionRecordPath"] = str(record_path.resolve())
    receipt["summaryPath"] = str(summary_path.resolve())
    return receipt

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="F3 一键多轮课堂模拟 Runner")
    parser.add_argument("--config", default="f3_demo_config.json")
    parser.add_argument("--rounds", type=int, default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--writeback-only", default=None, metavar="RUN_DIR",
                        help="只将已有 session_record.json/summary.md 回写 F2，不重新运行课堂")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = load_config(args.config)
        if args.writeback_only:
            receipt = writeback_to_f2(config, args.writeback_only)
            print("F2 回写完成")
            print("simulationRunId:", receipt["simulationRunId"])
            print("alreadySaved:", str(receipt["alreadySaved"]).lower())
            print("receipt:", receipt["receiptPath"])
            return 0

        record = run_demo(
            config,
            rounds_override=args.rounds,
            output_dir_override=args.output_dir,
        )
        print("==========================================")
        print("F3 简化 Runner 运行结束")
        print("F3 session_id:", record["f3SessionId"])
        print("完成轮数:", f"{record['completedRounds']}/{record['requestedRounds']}")
        print("最终状态:", record["status"])
        boundary = record["executionBoundary"]
        print("HTTP 链路:", boundary["httpChain"])
        print("F4 Provider:", boundary["f4Provider"])
        print("F3 模型内容:", boundary["f3ModelContent"])
        print("session_record.json:", record["sessionRecordPath"])
        print("summary.md:", record["summaryPath"])

        if record["status"] != "COMPLETED":
            print("==========================================")
            return 1

        if config["writebackToF2"]:
            try:
                run_dir = Path(record["sessionRecordPath"]).parent
                receipt = writeback_to_f2(config, run_dir)
                print("F2 simulationRunId:", receipt["simulationRunId"])
                print("F2 alreadySaved:", str(receipt["alreadySaved"]).lower())
                print("f2_writeback_receipt.json:", receipt["receiptPath"])
            except (ValueError, RuntimeError, requests.RequestException, KeyError, TypeError, OSError) as exc:
                print("模拟已完成、F2 保存失败，可使用 --writeback-only 重试:", exc)
                print("==========================================")
                return 1

        print("==========================================")
        return 0
    except (ValueError, RuntimeError, requests.RequestException, KeyError, TypeError, OSError) as exc:
        print("F3 Demo 启动失败:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
