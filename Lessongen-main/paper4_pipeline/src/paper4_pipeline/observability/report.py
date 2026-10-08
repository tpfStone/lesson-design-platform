"""Offline analysis and human-readable reporting for saved pipeline runs."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean

from paper4_pipeline.exporters.common import atomic_write_text


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _read_trace(path: Path) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"trace line {line_number} is not an object: {path}")
        events.append(value)
    return events


def analyze_artifacts(artifacts_root: Path) -> dict[str, object]:
    """Summarize saved runs and score distributions without calling a model."""

    result_paths = sorted(artifacts_root.rglob("run_result.json"))
    statuses: Counter[str] = Counter()
    stop_reasons: Counter[str] = Counter()
    scores: list[float] = []
    alignments: list[float] = []
    run_rows: list[dict[str, object]] = []
    unreadable: list[dict[str, str]] = []

    for path in result_paths:
        try:
            result = _read_json(path)
            statuses[str(result.get("status", "unknown"))] += 1
            stop_reasons[str(result.get("stop_reason", "unknown"))] += 1
            best_id = str(result.get("best_version_id", ""))
            versions = result.get("versions", [])
            best = next(
                (
                    item
                    for item in versions
                    if isinstance(item, dict) and str(item.get("version_id", "")) == best_id
                ),
                None,
            )
            score: float | None = None
            alignment: float | None = None
            if isinstance(best, dict) and isinstance(best.get("internal_evaluation"), dict):
                evaluation = best["internal_evaluation"]
                score = float(evaluation["overall_score"])
                rubric = evaluation.get("rubric_scores", {})
                if isinstance(rubric, dict) and "curriculum_alignment" in rubric:
                    alignment = float(rubric["curriculum_alignment"])
                scores.append(score)
                if alignment is not None:
                    alignments.append(alignment)
            run_rows.append(
                {
                    "run_id": result.get("run_id", path.parent.name),
                    "status": result.get("status"),
                    "stop_reason": result.get("stop_reason"),
                    "best_overall_score": score,
                    "best_curriculum_alignment": alignment,
                    "model_call_count": result.get("model_call_count", 0),
                    "estimated_cost": result.get("estimated_cost", 0),
                    "result_path": str(path.resolve()),
                }
            )
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            unreadable.append({"path": str(path.resolve()), "error": f"{type(exc).__name__}: {exc}"})

    def distribution(values: list[float]) -> dict[str, float | int | None]:
        return {
            "count": len(values),
            "minimum": min(values) if values else None,
            "mean": round(mean(values), 3) if values else None,
            "maximum": max(values) if values else None,
        }

    return {
        "analysis_version": "offline-run-analysis-v0.1",
        "artifacts_root": str(artifacts_root.resolve()),
        "model_calls_made": 0,
        "run_count": len(run_rows),
        "status_counts": dict(sorted(statuses.items())),
        "stop_reason_counts": dict(sorted(stop_reasons.items())),
        "best_score_distribution": distribution(scores),
        "best_curriculum_alignment_distribution": distribution(alignments),
        "runs": sorted(
            run_rows,
            key=lambda item: (
                item["best_overall_score"] is not None,
                item["best_overall_score"] or -1,
            ),
            reverse=True,
        ),
        "unreadable_results": unreadable,
    }


def render_process_report(run_dir: Path, *, include_payloads: bool = True) -> str:
    """Render one saved run as Markdown without replaying any agent."""

    result = _read_json(run_dir / "run_result.json")
    events = _read_trace(run_dir / "trace.jsonl")
    lines = [
        f"# 教案生成过程报告 · {result.get('run_id', run_dir.name)}",
        "",
        "> 本报告完全由已保存的 run_result.json 与 trace.jsonl 离线生成，"
        "不会调用模型，也不会伪造 Agent 输出。",
        "",
        "## 运行概览",
        "",
        "| 项目 | 值 |",
        "| --- | --- |",
        f"| 状态 | {result.get('status')} |",
        f"| 停止原因 | {result.get('stop_reason')} |",
        f"| 最佳版本 | {result.get('best_version_id')} |",
        f"| 最后版本 | {result.get('last_version_id')} |",
        f"| 模型调用 | {result.get('model_call_count', 0)} |",
        f"| 估算成本 | ${float(result.get('estimated_cost', 0)):.6f} |",
        f"| 事件数 | {len(events)} |",
        "",
        "## 版本评分",
        "",
        "| 版本 | 轮次 | 总分 | 最低维度 |",
        "| --- | ---: | ---: | --- |",
    ]
    for version in result.get("versions", []):
        if not isinstance(version, dict):
            continue
        evaluation = version.get("internal_evaluation")
        if not isinstance(evaluation, dict):
            lines.append(f"| {version.get('version_id')} | {version.get('iteration')} | — | — |")
            continue
        rubric = evaluation.get("rubric_scores", {})
        lowest = min(rubric.items(), key=lambda item: item[1]) if isinstance(rubric, dict) and rubric else ("—", "—")
        lines.append(
            f"| {version.get('version_id')} | {version.get('iteration')} | "
            f"{evaluation.get('overall_score')} | {lowest[0]}={lowest[1]} |"
        )

    lines.extend(["", "## 事件时间线", ""])
    for event in events:
        lines.extend(
            [
                f"### {int(event.get('sequence', 0)):02d}. {event.get('event_type', 'unknown')}",
                "",
                f"- 阶段/角色：`{event.get('stage', '')}` / `{event.get('actor_profile_id', '')}`",
                f"- 轮次/版本：{event.get('round_index', 0)} / `{event.get('version_id', '') or '—'}`",
                f"- 状态：{event.get('status', '')}",
                f"- 耗时/成本：{float(event.get('duration_seconds', 0)):.2f}s / ${float(event.get('estimated_cost', 0)):.6f}",
            ]
        )
        if event.get("error"):
            lines.append(f"- 错误：{event.get('error')}")
        if include_payloads:
            for label, key in (("输入", "input_summary"), ("输出", "output_summary")):
                payload = json.dumps(event.get(key), ensure_ascii=False, indent=2)
                lines.extend(["", f"**{label}**", "", "````json", payload, "````"])
        lines.append("")

    lines.extend(
        [
            "## 汇总记录",
            "",
            f"- 批评意见：{len(result.get('critiques', []))}",
            f"- 校验批次：{len(result.get('validation_batches', []))}",
            f"- 改写记录：{len(result.get('rewrite_records', []))}",
            f"- 路由决策：{len(result.get('route_decisions', []))}",
            "",
        ]
    )
    return "\n".join(lines)


def export_process_report(
    run_dir: Path,
    output: Path | None = None,
    *,
    include_payloads: bool = True,
) -> Path:
    target = output or run_dir / "generation_process.md"
    atomic_write_text(target, render_process_report(run_dir, include_payloads=include_payloads))
    return target
