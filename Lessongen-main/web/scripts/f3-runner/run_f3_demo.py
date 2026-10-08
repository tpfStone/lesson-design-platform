"""F3 formal session runner used by the F2 platform.

The filename is kept for backward-compatible Java configuration, but the
implementation uses the formal asynchronous F3 v3 Session API:

POST /api/classroom/sessions -> poll status -> POST /analyze -> GET /result.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import requests

from run_f4_to_f3_auto import build_f3_materials, get_f4_current_state, write_json_atomic

DEFAULT_TIMEOUT = 30


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _require_nonempty_string(data: Dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"配置字段 {key} 必须为非空字符串")
    return value.strip()


def _uuid(value: str, field: str) -> str:
    try:
        return str(UUID(value))
    except Exception as exc:
        raise ValueError(f"{field} 必须是 UUID: {value}") from exc


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
        "f2Url": str(data.get("f2Url") or "http://127.0.0.1:8080").strip(),
        "lessonId": _require_nonempty_string(data, "lessonId"),
        "versionId": _require_nonempty_string(data, "versionId"),
        "f4SessionId": _uuid(_require_nonempty_string(data, "f4SessionId"), "f4SessionId"),
        "outputDir": str(data.get("outputDir") or "outputs/f3_demo").strip(),
        "writebackToF2": data.get("writebackToF2", False),
        "requestKey": data.get("requestKey"),
        "modelMode": str(data.get("modelMode") or "REAL").strip().upper(),
        "timeoutSeconds": data.get("timeoutSeconds", 3),
        "maxConsecutiveTimeouts": data.get("maxConsecutiveTimeouts", 50),
        "maxEvents": data.get("maxEvents", 40),
        "maxWallClockSeconds": data.get("maxWallClockSeconds", 900),
        "activeRoles": data.get("activeRoles"),
        "liveStatusPath": data.get("liveStatusPath"),
    }
    if normalized["modelMode"] not in {"REAL", "MOCK"}:
        raise ValueError("modelMode 必须是 REAL 或 MOCK")
    if normalized["requestKey"] is not None:
        if not isinstance(normalized["requestKey"], str) or not normalized["requestKey"].strip():
            raise ValueError("requestKey 必须为非空字符串")
        normalized["requestKey"] = normalized["requestKey"].strip()
    for key in ("timeoutSeconds", "maxConsecutiveTimeouts", "maxEvents", "maxWallClockSeconds"):
        value = normalized[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{key} 必须是正整数")
    roles = normalized["activeRoles"]
    if roles is not None:
        allowed = {"teacher", "assistant", "class_clown", "deep_thinker", "note_taker", "inquisitive_mind"}
        if not isinstance(roles, list) or not roles or any(not isinstance(role, str) or role not in allowed for role in roles):
            raise ValueError("activeRoles 包含未知课堂角色")
        if "teacher" not in roles or len(set(roles)) != len(roles):
            raise ValueError("activeRoles 必须包含 teacher 且不能重复")
    live_path = normalized["liveStatusPath"]
    if live_path is not None and (not isinstance(live_path, str) or not live_path.strip()):
        raise ValueError("liveStatusPath 必须为非空路径")
    if not normalized["f2Url"]:
        raise ValueError("f2Url 必须为非空字符串")
    if not isinstance(normalized["writebackToF2"], bool):
        raise ValueError("writebackToF2 必须是 true/false")
    return normalized


def check_f4_service(session: requests.Session, f4_url: str) -> None:
    url = f"{f4_url.rstrip('/')}/api/health"
    try:
        response = session.get(url, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"无法访问 F4 服务，请检查 8000/F4 地址: {exc}") from exc
    if response.status_code == 404:
        return
    if not response.ok:
        raise RuntimeError(f"F4 健康检查失败: HTTP {response.status_code}")


def check_f3_service(session: requests.Session, f3_url: str) -> None:
    url = f"{f3_url.rstrip('/')}/api/health"
    try:
        response = session.get(url, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"无法访问 F3 服务，请检查 8003/F3 地址: {exc}") from exc
    if not response.ok:
        raise RuntimeError(f"F3 健康检查失败: HTTP {response.status_code}")
    data = response.json()
    if not isinstance(data, dict) or data.get("status") != "up":
        raise RuntimeError("F3 /api/health 未返回 status=up")


def _f4_provider(f4_state: Dict[str, Any]) -> str:
    snapshot = (f4_state.get("session") or {}).get("config_snapshot")
    if isinstance(snapshot, dict) and snapshot.get("provider"):
        return str(snapshot["provider"])
    return "UNKNOWN"


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


def _normalize_materials(materials: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for index, material in enumerate(materials, start=1):
        metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
        source_section_id = str(
            metadata.get("source_section_id")
            or metadata.get("sourceSectionId")
            or material.get("sourceSectionId")
            or material.get("id")
            or index
        )
        result.append(
            {
                "materialId": str(material.get("materialId") or material.get("id") or source_section_id),
                "title": str(material.get("title") or f"课堂材料 {index}"),
                "sourceSectionId": source_section_id,
                "teachingScript": str(
                    material.get("teachingScript")
                    or material.get("teaching_script")
                    or material.get("content")
                    or ""
                ),
                "keyPoints": material.get("keyPoints") or material.get("key_points") or [],
                "metadata": metadata,
            }
        )
    if not result:
        raise ValueError("Adapter 转换后没有可发送给 F3 的课堂 materials")
    return result


def start_f3_session(
    session: requests.Session,
    config: Dict[str, Any],
    f4_lesson_plan_id: str,
    materials: List[Dict[str, Any]],
) -> Dict[str, Any]:
    request_key = config.get("requestKey") or (
        f"f2:{config['lessonId']}:{config['versionId']}:{config['f4SessionId']}"
    )
    payload = {
        "lessonId": config["lessonId"],
        "versionId": config["versionId"],
        "modelMode": config["modelMode"],
        "requestKey": request_key,
        "timeoutSeconds": config["timeoutSeconds"],
        "maxConsecutiveTimeouts": config["maxConsecutiveTimeouts"],
        "maxEvents": config["maxEvents"],
        "maxWallClockSeconds": config["maxWallClockSeconds"],
        "source": {
            "module": "F4",
            "session_id": config["f4SessionId"],
            "lesson_plan_id": f4_lesson_plan_id,
        },
        "materials": materials,
    }
    if config.get("activeRoles") is not None:
        payload["activeRoles"] = config["activeRoles"]
    response = session.post(
        f"{config['f3Url'].rstrip('/')}/api/classroom/sessions",
        json=payload,
        timeout=DEFAULT_TIMEOUT,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(f"F3 /sessions 状态码: {response.status_code} {response.text[:1000]}")
    data = response.json()
    if not isinstance(data, dict) or not data.get("sessionId"):
        raise RuntimeError("F3 /sessions 未返回 sessionId")
    if data.get("lessonId") != config["lessonId"] or data.get("versionId") != config["versionId"]:
        raise RuntimeError("F3 /sessions 返回 lessonId/versionId 不一致")
    if str(data.get("modelMode", "")).upper() != config["modelMode"]:
        raise RuntimeError("F3 /sessions 返回 modelMode 与请求不一致")
    return data


def poll_completed(session: requests.Session, f3_url: str, session_id: str, max_seconds: int) -> Dict[str, Any]:
    deadline = time.monotonic() + max_seconds + 60
    last: Dict[str, Any] = {}
    last_transport_error = ""
    while time.monotonic() < deadline:
        try:
            response = session.get(
                f"{f3_url.rstrip('/')}/api/classroom/sessions/{session_id}",
                timeout=60,
            )
        except requests.RequestException as exc:
            last_transport_error = f"{type(exc).__name__}: {exc}"
            time.sleep(2)
            continue

        if not response.ok:
            if response.status_code >= 500:
                last_transport_error = f"HTTP {response.status_code}: {response.text[:300]}"
                time.sleep(2)
                continue
            raise RuntimeError(f"F3 session 状态查询失败: HTTP {response.status_code} {response.text[:1000]}")

        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("F3 session 状态返回不是 JSON 对象")

        last = data
        status = str(data.get("status") or "").upper()

        if status == "COMPLETED":
            return data
        if status == "INTERRUPTED" and data.get("stopReason") == "MANUAL_END":
            return data
        if status in {"FAILED", "INTERRUPTED"}:
            raise RuntimeError(f"F3 session 失败: {status} {json.dumps(data, ensure_ascii=False)[:1000]}")

        time.sleep(2)

    suffix = f"；最后通信错误: {last_transport_error}" if last_transport_error else ""
    raise RuntimeError(f"等待 F3 session COMPLETED 超时，最后状态: {last.get('status')}{suffix}")


def _analysis_artifact_ready(result: Dict[str, Any]) -> bool:
    artifacts = result.get("artifacts")
    return isinstance(artifacts, list) and "issue_analysis.json" in artifacts


def analyze_session(session: requests.Session, f3_url: str, session_id: str) -> None:
    last_error = ""
    for attempt in range(3):
        try:
            response = session.post(
                f"{f3_url.rstrip('/')}/api/classroom/sessions/{session_id}/analyze",
                timeout=180,
            )
            if response.ok:
                return
            if response.status_code < 500:
                raise RuntimeError(
                    f"F3 /analyze 失败: HTTP {response.status_code} {response.text[:1000]}"
                )
            last_error = f"HTTP {response.status_code} {response.text[:500]}"
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        try:
            if _analysis_artifact_ready(get_result(session, f3_url, session_id, attempts=1)):
                return
        except (RuntimeError, requests.RequestException):
            pass
        if attempt < 2:
            time.sleep(3)
    raise RuntimeError(f"F3 /analyze 多次未完成: {last_error}")


def get_result(session: requests.Session, f3_url: str, session_id: str,
               *, attempts: int = 5) -> Dict[str, Any]:
    last_error = ""
    for attempt in range(attempts):
        try:
            response = session.get(
                f"{f3_url.rstrip('/')}/api/classroom/sessions/{session_id}/result",
                timeout=180,
            )
            if response.ok:
                data = response.json()
                if not isinstance(data, dict):
                    raise RuntimeError("F3 /result 返回不是 JSON 对象")
                return data
            if response.status_code < 500:
                raise RuntimeError(
                    f"F3 /result 失败: HTTP {response.status_code} {response.text[:1000]}"
                )
            last_error = f"HTTP {response.status_code} {response.text[:500]}"
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt + 1 < attempts:
            time.sleep(3)
    raise RuntimeError(f"F3 /result 多次未完成: {last_error}")


def recover_terminal_result(session: requests.Session, f3_url: str, session_id: str
                            ) -> tuple[Dict[str, Any], Dict[str, Any]] | None:
    try:
        response = session.get(
            f"{f3_url.rstrip('/')}/api/classroom/sessions/{session_id}",
            timeout=180,
        )
        if not response.ok:
            return None
        state = response.json()
        status = str(state.get("status") or "").upper()
        if status not in {"COMPLETED", "INTERRUPTED"}:
            return None
        return state, get_result(session, f3_url, session_id)
    except (requests.RequestException, RuntimeError, ValueError, TypeError):
        return None


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
    materials: List[Dict[str, Any]],
    final_state: Dict[str, Any],
    f4_state: Dict[str, Any],
    f3_result: Optional[Dict[str, Any]] = None,
    error: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    f3_result = f3_result or {}
    events = f3_result.get("events") if isinstance(f3_result.get("events"), list) else []
    statistics = f3_result.get("statistics") if isinstance(f3_result.get("statistics"), dict) else {}
    summary = f3_result.get("summary") if isinstance(f3_result.get("summary"), dict) else {}
    issues = f3_result.get("issues") if isinstance(f3_result.get("issues"), list) else []
    action_items = f3_result.get("actionItems") if isinstance(f3_result.get("actionItems"), list) else []
    warnings = f3_result.get("analysisWarnings") if isinstance(f3_result.get("analysisWarnings"), list) else []
    model_mode = str(
    f3_result.get("modelMode")
    or (f3_result.get("session") or {}).get("modelMode")
    or final_state.get("modelMode")
    or "REAL"
).upper()
    history = [
        {
            "speaker": event.get("speaker"),
            "function": event.get("function"),
            "content": event.get("content", ""),
        }
        for event in events
        if isinstance(event, dict) and str(event.get("status", "")).upper() == "COMPLETED"
    ]
    result: Dict[str, Any] = {
        "status": status,
        "modelMode": model_mode,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "lessonId": lesson_id,
        "versionId": version_id,
        "f4SessionId": f4_session_id,
        "f4LessonPlanId": f4_lesson_plan_id,
        "f3SessionId": f3_session_id,
        "requestedRounds": 0,
        "completedRounds": 0,
        "materialCount": len(materials),
        "materials": materials,
        "rounds": [],
        "finalState": {**final_state, "history": history},
        "events": events,
        "statistics": statistics,
        "summary": summary,
        "issues": issues,
        "actionItems": action_items,
        "analysisWarnings": warnings,
        "session": {
            "activeRoles": (f3_result.get("session") or {}).get("activeRoles", []),
            "modelMode": model_mode,
            "status": status,
        },
        "executionBoundary": {
            "httpChain": "REAL",
            "f4Provider": _f4_provider(f4_state),
            "f3ModelContent": model_mode,
            "note": "F3 is called through the formal asynchronous Session API.",
        },
    }
    if error is not None:
        result["error"] = error
    return result


def build_summary(record: Dict[str, Any]) -> str:
    def excerpt(value: Any, limit: int = 2000) -> str:
        content = str(value or "")
        return content if len(content) <= limit else content[:limit] + "……（完整内容见 JSON 记录）"

    events = record.get("events") or []
    issues = record.get("issues") or []
    actions = record.get("actionItems") or []
    roles = {
        "teacher": "教师", "assistant": "协作支持型", "class_clown": "活跃互动型",
        "deep_thinker": "深度思考型", "note_taker": "认真记录型",
        "inquisitive_mind": "好奇提问型",
    }
    status = "已完成" if record["status"] == "COMPLETED" else "提前结束"
    lines: List[str] = [
        "# 课堂推演简报",
        "",
        f"- 课堂状态：**{status}**",
        f"- 课堂事件：{len(events)} 个",
        f"- 教学环节：{record['materialCount']} 个",
        f"- 发现的问题：{len(issues)} 项",
        "",
        "## 教学环节",
        "",
    ]
    for material in record.get("materials", []):
        lines.append(f"- {excerpt(material.get('title') or '教学环节', 120)}")
    lines.extend(["", "## 课堂记录", ""])
    for event in events:
        trigger = event.get("trigger") or {}
        if trigger.get("type") == "USER_INPUT" and trigger.get("content"):
            lines.extend(["### 教师输入", "", excerpt(trigger["content"]), ""])
        speaker = event.get("roleLabel") or roles.get(event.get("speaker"), "课堂参与者")
        lines.extend([f"### {speaker}", "", excerpt(event.get("content") or "课堂推进至下一环节。"), ""])
    lines.extend(["## 发现的问题", ""])
    if not issues:
        lines.extend(["本次没有通过分析校验的课堂问题。", ""])
    for issue in issues:
        lines.extend([f"### {excerpt(issue.get('title') or '课堂问题', 120)}", "", excerpt(issue.get("problem")), ""])
        if issue.get("suggestedAction"):
            lines.extend(["**改进建议：** " + excerpt(issue["suggestedAction"]), ""])
    if actions:
        lines.extend(["## 后续改进建议", ""])
        for item in actions:
            if item.get("action"):
                lines.append("- " + excerpt(item["action"]))
        lines.append("")
    if record.get("modelMode") == "MOCK":
        lines.extend(["> 本次采用模拟回复，仅供流程测试。", ""])
    if record.get("status") == "FAILED":
        error = record.get("error") or {}
        lines.extend(["## 未完成原因", "", str(error.get("message") or "课堂未能完成。")])
    return "\n".join(lines) + "\n"


def run_demo(config: Dict[str, Any], *, http_session: Optional[requests.Session] = None,
             rounds_override: Optional[int] = None, output_dir_override: Optional[str] = None) -> Dict[str, Any]:
    del rounds_override
    config = dict(config)
    if output_dir_override is not None:
        if not output_dir_override.strip():
            raise ValueError("--output-dir 不得为空")
        config["outputDir"] = output_dir_override.strip()

    session = http_session or requests.Session()
    started_at = _now_iso()
    check_f4_service(session, config["f4Url"])
    check_f3_service(session, config["f3Url"])

    f4_state = get_f4_current_state(config["f4Url"], config["f4SessionId"], http_session=session)
    f4_lesson_plan_id = _uuid(str(f4_state["lesson_plan"]["id"]), "f4LessonPlanId")
    materials = _normalize_materials(build_f3_materials(f4_state))

    start_data = start_f3_session(session, config, f4_lesson_plan_id, materials)
    f3_session_id = _uuid(str(start_data["sessionId"]), "f3SessionId")
    if config.get("liveStatusPath"):
        write_json_atomic(config["liveStatusPath"], {
            "sessionId": f3_session_id,
            "lessonId": config["lessonId"],
            "versionId": config["versionId"],
        })
    run_dir = create_run_dir(config["outputDir"], f3_session_id)
    record_path = run_dir / "session_record.json"
    summary_path = run_dir / "summary.md"

    last_state: Dict[str, Any] = {}
    f3_result: Dict[str, Any] = {}
    failure: Optional[Dict[str, Any]] = None
    try:
        last_state = poll_completed(session, config["f3Url"], f3_session_id, config["maxWallClockSeconds"])
        preliminary = get_result(session, config["f3Url"], f3_session_id)
        if not _analysis_artifact_ready(preliminary):
            analyze_session(session, config["f3Url"], f3_session_id)
        f3_result = get_result(session, config["f3Url"], f3_session_id)
        status = str(last_state.get("status") or "COMPLETED")
    except Exception as exc:
        failure = {"type": type(exc).__name__, "message": str(exc)}
        recovered = recover_terminal_result(session, config["f3Url"], f3_session_id)
        if recovered is None:
            status = "FAILED"
        else:
            last_state, f3_result = recovered
            status = str(last_state.get("status") or "COMPLETED").upper()
            warnings = f3_result.get("analysisWarnings")
            if not isinstance(warnings, list):
                warnings = []
                f3_result["analysisWarnings"] = warnings
            warnings.append("总平台读取最终分析时发生短暂异常，已从 F3 终态结果恢复：" + str(exc))
            failure = None

    record = build_session_record(
        status=status,
        started_at=started_at,
        finished_at=_now_iso(),
        lesson_id=config["lessonId"],
        version_id=config["versionId"],
        f4_session_id=config["f4SessionId"],
        f4_lesson_plan_id=f4_lesson_plan_id,
        f3_session_id=f3_session_id,
        materials=materials,
        final_state=last_state,
        f4_state=f4_state,
        f3_result=f3_result,
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
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("session_record.json 顶层必须是 JSON 对象")
    summary = summary_path.read_text(encoding="utf-8")
    if not summary.strip():
        raise ValueError("summary.md 不能为空")
    return record_path, summary_path, record, summary


def writeback_to_f2(config: Dict[str, Any], run_dir: str | Path,
                    *, http_session: Optional[requests.Session] = None) -> Dict[str, Any]:
    session = http_session or requests.Session()
    record_path, summary_path, record, summary = _load_local_artifacts(run_dir)
    if record.get("status") not in {"COMPLETED", "INTERRUPTED"}:
        raise RuntimeError("只有已结束的课堂模拟结果才能回写 F2")

    lesson_id = str(record.get("lessonId") or "").strip()
    version_id = str(record.get("versionId") or "").strip()
    f3_session_id = str(record.get("f3SessionId") or "").strip()
    if not lesson_id or not version_id or not f3_session_id:
        raise ValueError("本地结果缺少 lessonId/versionId/f3SessionId")
    if config.get("lessonId") and config["lessonId"] != lesson_id:
        raise ValueError("配置 lessonId 与本地结果不一致")
    if config.get("versionId") and config["versionId"] != version_id:
        raise ValueError("配置 versionId 与本地结果不一致")

    url = f"{config['f2Url'].rstrip('/')}/api/platform/lessons/{lesson_id}/simulations"
    response = session.post(url, json={"sessionRecord": record, "summaryMarkdown": summary}, timeout=DEFAULT_TIMEOUT)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"模拟已完成、F2 保存失败，可重试回写: HTTP {response.status_code} {response.text[:1000]}")
    data = response.json()
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
    parser = argparse.ArgumentParser(description="F3 正式课堂模拟 Session Runner")
    parser.add_argument("--config", default="f3_demo_config.json")
    parser.add_argument("--rounds", type=int, default=None, help="兼容旧参数；正式 Session API 不使用固定轮数")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--writeback-only", default=None, metavar="RUN_DIR")
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

        record = run_demo(config, rounds_override=args.rounds, output_dir_override=args.output_dir)
        print("==========================================")
        print("F3 正式 Session Runner 运行结束")
        print("F3 session_id:", record["f3SessionId"])
        print("modelMode:", record.get("modelMode"))
        print("动态事件数:", len(record.get("events") or []))
        print("问题数:", len(record.get("issues") or []))
        print("最终状态:", record["status"])
        boundary = record["executionBoundary"]
        print("HTTP 链路:", boundary["httpChain"])
        print("F4 Provider:", boundary["f4Provider"])
        print("F3 模型内容:", boundary["f3ModelContent"])
        print("session_record.json:", record["sessionRecordPath"])
        print("summary.md:", record["summaryPath"])
        if record["status"] not in {"COMPLETED", "INTERRUPTED"}:
            print("==========================================")
            return 1
        if config["writebackToF2"]:
            receipt = writeback_to_f2(config, Path(record["sessionRecordPath"]).parent)
            print("F2 simulationRunId:", receipt["simulationRunId"])
            print("F2 alreadySaved:", str(receipt["alreadySaved"]).lower())
            print("f2_writeback_receipt.json:", receipt["receiptPath"])
        print("==========================================")
        return 0
    except (ValueError, RuntimeError, requests.RequestException, KeyError, TypeError, OSError) as exc:
        print("F3 Session Runner 启动失败:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
