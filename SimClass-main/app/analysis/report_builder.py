from __future__ import annotations

from collections import Counter
from typing import Any

from app.contracts.analysis import AnalysisResult
from app.contracts.event import ClassroomEventRecord


ROLE_LABELS = {
    "teacher": "教师",
    "assistant": "助教",
    "class_clown": "活跃同学",
    "deep_thinker": "深度思考者",
    "note_taker": "笔记员",
    "inquisitive_mind": "好奇提问者",
    "user": "用户",
}


def build_statistics(
    events: list[ClassroomEventRecord],
    materials: list[dict[str, Any]],
) -> dict[str, Any]:
    completed = [e for e in events if e.status == "COMPLETED"]
    role_counts = Counter(e.speaker for e in completed if e.speaker)
    function_counts = Counter(e.function for e in completed if e.function)
    covered_ids = {
        e.material.material_id
        for e in completed
        if e.material is not None
    }
    material_coverage = [
        {
            "materialId": str(m.get("materialId", m.get("id", ""))),
            "title": m.get("title"),
            "covered": str(m.get("materialId", m.get("id", ""))) in covered_ids,
        }
        for m in materials
    ]
    return {
        "eventCount": len(events),
        "roleCounts": dict(role_counts),
        "functionCounts": dict(function_counts),
        "materialCoverage": material_coverage,
        "observedWallClockSeconds": round(
            sum(e.wall_clock_duration_ms for e in events) / 1000.0, 3
        ),
        # Deliberately null: request latency is not teaching time.
        "estimatedTeachingSeconds": None,
    }


def build_summary(
    *,
    session: dict[str, Any],
    events: list[ClassroomEventRecord],
    statistics: dict[str, Any],
) -> dict[str, Any]:
    completed = [e for e in events if e.status == "COMPLETED"]
    return {
        "title": "F3 课堂模拟简报",
        "status": session.get("status"),
        "stopReason": session.get("stopReason"),
        "eventCount": len(events),
        "completedEventCount": len(completed),
        "rolesObserved": sorted(statistics.get("roleCounts", {}).keys()),
        "materialsCovered": [
            item["title"]
            for item in statistics.get("materialCoverage", [])
            if item.get("covered")
        ],
        "lastEvent": (
            completed[-1].model_dump(by_alias=True) if completed else None
        ),
        "note": "wallClockDurationMs is system execution time, not estimated classroom teaching time.",
    }


def _event_trigger_text(event: dict[str, Any]) -> str:
    trigger = event.get("trigger") or {}
    trigger_type = str(trigger.get("type") or "UNKNOWN")
    content = trigger.get("content")
    if trigger_type == "USER_INPUT":
        return f"用户输入：{content}" if content else "用户输入"
    if trigger_type == "TIMEOUT":
        return "等待用户输入超时，由 Manager 根据当前课堂状态自主推进。"
    if trigger_type == "INITIALIZATION":
        return "课堂启动，开始当前教学材料。"
    if content:
        return f"{trigger_type}：{content}"
    return trigger_type


def _material_line(material: dict[str, Any] | None) -> str:
    if not material:
        return "未绑定材料"
    title = material.get("title") or "未命名材料"
    material_id = material.get("materialId") or ""
    section_id = material.get("sourceSectionId")
    details = []
    if material_id:
        details.append(f"materialId=`{material_id}`")
    if section_id:
        details.append(f"sourceSectionId=`{section_id}`")
    if details:
        return f"{title} ({', '.join(details)})"
    return str(title)


def render_summary_markdown(result: dict[str, Any]) -> str:
    """Render a human-readable classroom-process brief.

    The formal JSON artifacts remain the machine-readable source of truth.  This
    markdown deliberately favors the old SimClass report's readability: session
    overview, materials, then one section per real classroom event.  Unlike the
    legacy four-round runner, the number of rounds is dynamic and comes directly
    from EventStore.
    """
    session = result["session"]
    stats = result["statistics"]
    summary = result["summary"]
    events = result.get("events") or []
    materials = session.get("materials") or []

    completed_count = sum(1 for e in events if e.get("status") == "COMPLETED")
    lines = [
        "# F3 课堂模拟简报",
        "",
        f"- 运行状态：**{session.get('status')}**",
        f"- 开始时间：{session.get('startedAt') or '未记录'}",
        f"- 结束时间：{session.get('finishedAt') or '未结束'}",
        f"- lessonId：`{session.get('lessonId')}`",
        f"- versionId：`{session.get('versionId')}`",
        f"- F3 sessionId：`{session.get('sessionId')}`",
        f"- 模型模式：**{session.get('modelMode')}**",
        f"- 模型 Provider：`{session.get('modelProvider') or '未记录'}`",
        f"- 模型名称：`{session.get('modelName') or '未记录'}`",
        f"- 课堂材料数：{len(materials)}",
        f"- 课堂事件数：{len(events)}",
        f"- 完成事件数：{completed_count}",
        f"- 停止原因：`{session.get('stopReason') or '未停止'}`",
        "",
        "## 课堂材料",
        "",
    ]

    if materials:
        for index, material in enumerate(materials, 1):
            title = material.get("title") or f"材料 {index}"
            material_id = material.get("materialId") or material.get("id") or ""
            source_section_id = material.get("sourceSectionId")
            suffix = []
            if material_id:
                suffix.append(f"materialId=`{material_id}`")
            if source_section_id:
                suffix.append(f"sourceSectionId=`{source_section_id}`")
            if suffix:
                lines.append(f"- {index}. {title} ({', '.join(suffix)})")
            else:
                lines.append(f"- {index}. {title}")
    else:
        lines.append("- 无")

    lines.extend(["", "## 各轮记录", ""])

    if not events:
        lines.append("当前没有课堂事件。")
    else:
        for event in events:
            sequence = event.get("sequence") or "?"
            speaker = event.get("speaker") or "unknown"
            role_label = event.get("roleLabel") or ROLE_LABELS.get(speaker, speaker)
            function = event.get("function") or "unknown"
            manager = event.get("managerDecision") or {}
            content = str(event.get("content") or "").strip()
            status = event.get("status") or "UNKNOWN"
            material = event.get("material")
            duration_ms = event.get("wallClockDurationMs")

            lines.extend(
                [
                    f"### 第 {sequence} 轮",
                    "",
                    f"- 触发：{_event_trigger_text(event)}",
                    f"- 对应材料：{_material_line(material)}",
                    f"- 发言角色：{role_label} (`{speaker}`)",
                    f"- 动作类型：`{function}`",
                ]
            )

            if manager:
                reason = str(manager.get("reason") or "").strip()
                decision = (
                    f"{manager.get('speaker') or speaker} / "
                    f"{manager.get('function') or function}"
                )
                if reason:
                    lines.append(f"- Manager 决策：`{decision}`；原因：{reason}")
                else:
                    lines.append(f"- Manager 决策：`{decision}`")

            lines.extend(["- 回复：", ""])
            if content:
                lines.extend(content.splitlines())
            else:
                lines.append("（本轮无文本输出）")

            lines.extend(
                [
                    "",
                    f"- 本轮结束状态：`{status}`",
                    f"- 真实系统执行耗时：{duration_ms if duration_ms is not None else '未记录'} ms",
                    "",
                ]
            )

    lines.extend(
        [
            "## 课堂统计",
            "",
            f"- 事件数：{stats['eventCount']}",
            f"- 系统真实执行耗时（秒）：{stats['observedWallClockSeconds']}",
            "- 估算教学时长：未估算（不得用模型请求耗时替代）",
            f"- 角色覆盖：{', '.join(summary['rolesObserved']) or '无'}",
            f"- 材料覆盖：{', '.join(summary['materialsCovered']) or '无'}",
            "",
            "### 角色计数",
            "",
        ]
    )
    for role, count in stats["roleCounts"].items():
        lines.append(f"- {ROLE_LABELS.get(role, role)} (`{role}`): {count}")

    lines.extend(["", "### Function 计数", ""])
    for func, count in stats["functionCounts"].items():
        lines.append(f"- `{func}`: {count}")

    lines.extend(
        [
            "",
            "## REAL / MOCK 边界",
            "",
            f"- F3 模型模式：`{session.get('modelMode')}`",
            f"- Provider：`{session.get('modelProvider') or '未记录'}`",
            f"- 模型：`{session.get('modelName') or '未记录'}`",
            "",
            "> 本简报中的课堂轮次直接来自 EventStore 的真实事件；wallClockDurationMs 仅表示系统/模型执行耗时，不代表真实课堂教学时长。",
            "",
        ]
    )
    return "\n".join(lines)


def render_action_items_markdown(analysis: AnalysisResult) -> str:
    lines = ["# F3 行动建议", ""]
    if analysis.model_mode:
        lines.extend([f"- modelMode: **{analysis.model_mode}**", ""])
    if not analysis.action_items:
        lines.append("当前没有通过证据验证的行动建议。")
    else:
        for item in analysis.action_items:
            lines.extend(
                [
                    f"## {item['actionId']} · {item['priority']}",
                    "",
                    f"- 来源问题: `{item['sourceIssueId']}`",
                    f"- 目标环节: {item.get('targetLessonSection') or '未定位'}",
                    f"- 建议: {item['action']}",
                    "",
                ]
            )
    if analysis.warnings:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {warning}" for warning in analysis.warnings)
    return "\n".join(lines) + "\n"
