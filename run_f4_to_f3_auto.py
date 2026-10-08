"""
F4 -> F3 contract runner

真实 HTTP 链路：
F4 /current-state -> Adapter -> F3 /start -> optional /message -> F3 /state

业务身份必须分离：
- F2 lessonId
- F2 versionId
- F4 session.id
- F4 lesson_plan.id
- F3 session_id
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from adapters.f4_f3_adapter import convert_f4_sections_to_f3_materials


def get_f4_current_state(
    f4_base_url: str,
    f4_session_id: str,
    timeout: int = 30,
    http_session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    url = f"{f4_base_url.rstrip('/')}/api/sessions/{f4_session_id}/current-state"
    client = http_session or requests
    response = client.get(url, timeout=timeout)

    print("F4 /current-state 状态码:", response.status_code)
    if not response.ok:
        print("F4 /current-state 返回:", response.text)
        response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("F4 current-state 返回不是 JSON 对象")

    session = data.get("session")
    lesson_plan = data.get("lesson_plan")
    sections = data.get("sections")

    if not isinstance(session, dict) or not session.get("id"):
        raise ValueError("F4 current-state 中没有有效的 session.id")
    if str(session["id"]) != str(f4_session_id):
        raise ValueError(
            f"F4 session ID 不一致: 参数={f4_session_id}, 返回={session['id']}"
        )
    if not isinstance(lesson_plan, dict) or not lesson_plan.get("id"):
        raise ValueError("F4 current-state 中没有有效的 lesson_plan.id")
    if not isinstance(sections, list):
        raise ValueError("F4 current-state 中没有有效的 sections 列表")

    return data


def build_f3_materials(f4_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    materials = convert_f4_sections_to_f3_materials(f4_state["sections"])
    if not materials:
        raise ValueError("Adapter 转换后没有可发送给 F3 的课堂 materials")
    return materials


def start_f3_classroom(
    f3_base_url: str,
    lesson_id: str,
    version_id: str,
    f4_session_id: str,
    f4_lesson_plan_id: str,
    materials: List[Dict[str, Any]],
    timeout: int = 30,
    http_session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    url = f"{f3_base_url.rstrip('/')}/api/classroom/start"
    payload = {
        "lesson_id": lesson_id,
        "version_id": version_id,
        "source": {
            "module": "F4",
            "session_id": f4_session_id,
            "lesson_plan_id": f4_lesson_plan_id,
        },
        "materials": materials,
    }

    client = http_session or requests
    response = client.post(url, json=payload, timeout=timeout)
    print("F3 /start 状态码:", response.status_code)
    print("F3 /start 返回:", response.text)
    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("F3 /start 返回不是有效 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("F3 /start 返回不是 JSON 对象")
    if not data.get("session_id"):
        raise ValueError("F3 /start 返回中没有 session_id")
    return data


def send_f3_message(
    f3_base_url: str,
    f3_session_id: str,
    message: str,
    timeout: int = 30,
    http_session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    url = f"{f3_base_url.rstrip('/')}/api/classroom/message"
    client = http_session or requests
    response = client.post(
        url,
        json={"session_id": f3_session_id, "message": message},
        timeout=timeout,
    )
    print("F3 /message 状态码:", response.status_code)
    print("F3 /message 返回:", response.text)
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("F3 /message 返回不是有效 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("F3 /message 返回不是 JSON 对象")
    for key in ("speaker", "function", "content"):
        if key not in data:
            raise ValueError(f"F3 /message 返回缺少字段: {key}")
    return data


def get_f3_state(
    f3_base_url: str,
    f3_session_id: str,
    timeout: int = 30,
    http_session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    url = f"{f3_base_url.rstrip('/')}/api/classroom/{f3_session_id}/state"
    client = http_session or requests
    response = client.get(url, timeout=timeout)
    print("F3 /state 状态码:", response.status_code)
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("F3 /state 返回不是有效 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("F3 /state 返回不是 JSON 对象")
    print("F3 /state 返回:")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return data


def _expected_mapping(
    lesson_id: str,
    version_id: str,
    f4_session_id: str,
    f4_lesson_plan_id: str,
) -> Dict[str, Any]:
    return {
        "lesson_id": lesson_id,
        "version_id": version_id,
        "source": {
            "module": "F4",
            "session_id": f4_session_id,
            "lesson_plan_id": f4_lesson_plan_id,
        },
    }


def verify_f3_mapping(
    start_data: Dict[str, Any],
    state_data: Dict[str, Any],
    lesson_id: str,
    version_id: str,
    f4_session_id: str,
    f4_lesson_plan_id: str,
) -> None:
    expected = _expected_mapping(
        lesson_id, version_id, f4_session_id, f4_lesson_plan_id
    )

    for name, data in (("F3 /start", start_data), ("F3 /state", state_data)):
        for key in ("lesson_id", "version_id", "source"):
            if data.get(key) != expected[key]:
                raise ValueError(
                    f"{name} 身份映射不一致: {key}; "
                    f"expected={expected[key]!r}, actual={data.get(key)!r}"
                )

    if state_data.get("session_id") != start_data.get("session_id"):
        raise ValueError("F3 /start 与 /state 的 session_id 不一致")


def _source_sections(materials: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for item in materials:
        metadata = item.get("metadata") or {}
        result.append(
            {
                "sourceSectionId": metadata.get("source_section_id"),
                "materialId": item.get("id"),
                "sectionType": metadata.get("source_section_type"),
                "sourceOrderIndex": metadata.get("source_order_index"),
            }
        )
    return result


def _model_content_mode(message_data: Optional[Dict[str, Any]]) -> str:
    if message_data is None:
        return "NOT_TESTED"
    content = str(message_data.get("content", ""))
    if "[MockLLM]" in content:
        return "MOCK"
    # 不根据“没有 Mock 标记”反推真实模型，避免伪造结论。
    return "UNVERIFIED"


def build_handoff_result(
    lesson_id: str,
    version_id: str,
    f4_session_id: str,
    f4_lesson_plan_id: str,
    f3_session_id: str,
    materials: List[Dict[str, Any]],
    f4_state: Dict[str, Any],
    message_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    config_snapshot = (f4_state.get("session") or {}).get("config_snapshot") or {}
    return {
        "status": "COMPLETED",
        "lessonId": lesson_id,
        "versionId": version_id,
        "f4SessionId": f4_session_id,
        "f4LessonPlanId": f4_lesson_plan_id,
        "f3SessionId": f3_session_id,
        "materialCount": len(materials),
        "sourceSections": _source_sections(materials),
        "f3StateVerified": True,
        "executionBoundary": {
            "httpChain": "REAL",
            "f4Provider": config_snapshot.get("provider", "UNKNOWN"),
            "f3ModelContent": _model_content_mode(message_data),
            "note": (
                "HTTP/F4 workflow/F3 API calls are real when this file is produced by "
                "a successful live run. Model-generated content may still be Mock."
            ),
        },
    }


def write_json_atomic(path: str | Path, data: Dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=str(output.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, output)
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise


def run_handoff(
    *,
    f4_url: str,
    f3_url: str,
    lesson_id: str,
    version_id: str,
    f4_session_id: str,
    message: Optional[str] = None,
    output: str = "f4_f3_handoff_result.json",
) -> Dict[str, Any]:
    # 避免失败时遗留旧的 COMPLETED 证据文件。
    output_path = Path(output)
    if output_path.exists():
        output_path.unlink()

    f4_state = get_f4_current_state(f4_url, f4_session_id)
    f4_lesson_plan_id = str(f4_state["lesson_plan"]["id"])

    print("F2 lessonId:", lesson_id)
    print("F2 versionId:", version_id)
    print("F4 session.id:", f4_session_id)
    print("F4 lesson_plan.id:", f4_lesson_plan_id)

    materials = build_f3_materials(f4_state)
    print("F4 sections 数量:", len(f4_state["sections"]))
    print("Adapter 转换后的 F3 materials 数量:", len(materials))

    start_data = start_f3_classroom(
        f3_url,
        lesson_id,
        version_id,
        f4_session_id,
        f4_lesson_plan_id,
        materials,
    )
    f3_session_id = str(start_data["session_id"])

    message_data = None
    if message:
        message_data = send_f3_message(f3_url, f3_session_id, message)

    # 按任务书要求：即使没有 --message，也必须调用 /state 验证身份映射。
    state_data = get_f3_state(f3_url, f3_session_id)
    verify_f3_mapping(
        start_data,
        state_data,
        lesson_id,
        version_id,
        f4_session_id,
        f4_lesson_plan_id,
    )

    result = build_handoff_result(
        lesson_id,
        version_id,
        f4_session_id,
        f4_lesson_plan_id,
        f3_session_id,
        materials,
        f4_state,
        message_data,
    )
    write_json_atomic(output_path, result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="F4 current-state -> Adapter -> F3 contract runner"
    )
    parser.add_argument("--f4-url", required=True)
    parser.add_argument("--f3-url", default="http://127.0.0.1:8003")
    parser.add_argument("--lesson-id", required=True, help="F2 lessonId")
    parser.add_argument("--version-id", required=True, help="F2 versionId")
    parser.add_argument("--f4-session-id", required=True, help="F4 current-state.session.id")
    parser.add_argument("--message", default=None)
    parser.add_argument(
        "--output",
        default="f4_f3_handoff_result.json",
        help="联调结果 JSON 路径",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        print("==========================================")
        print("开始 F4 -> F3 身份映射固化联调")
        print("==========================================")
        result = run_handoff(
            f4_url=args.f4_url,
            f3_url=args.f3_url,
            lesson_id=args.lesson_id,
            version_id=args.version_id,
            f4_session_id=args.f4_session_id,
            message=args.message,
            output=args.output,
        )
        print("==========================================")
        print("F4 -> F3 联调固化完成")
        print("F3 session_id:", result["f3SessionId"])
        print("结果文件:", args.output)
        print("==========================================")
        return 0
    except requests.RequestException as exc:
        print("HTTP 请求失败:", exc)
        return 1
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print("联调失败:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
