"""Friendly command-line entry point for live lesson-plan generation."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Callable
from pathlib import Path

from dotenv import load_dotenv

from paper4_pipeline.agents.profiles import default_profile_registry
from paper4_pipeline.control.evidence import build_task_evidence_profile
from paper4_pipeline.domain.models import ExperimentConfig, LessonTask
from paper4_pipeline.domain.naming import automatic_run_id, automatic_task_id
from paper4_pipeline.exporters.common import atomic_write_text
from paper4_pipeline.observability.report import (
    analyze_artifacts,
    export_process_report,
)
from paper4_pipeline.providers.openai_compatible import OpenAICompatibleProvider
from paper4_pipeline.service import PipelineService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT.parent / ".env", override=False)
load_dotenv(PROJECT_ROOT / ".env", override=False)
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "deepseek_v4_flash.json"
DEFAULT_OUTPUT = Path(
    os.getenv(
        "PAPER4_ARTIFACTS_ROOT",
        str(PROJECT_ROOT / "artifacts"),
    )
).expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lessongen Paper#4 真实多智能体教案生成器"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser(
        "generate",
        help="交互输入科目、年级和课题并直接生成教案（推荐）",
    )
    generate.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    generate.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    generate.add_argument(
        "--run-name",
        default=None,
        help="可选短名称；最终目录仍会自动添加时间和防冲突后缀",
    )
    generate.add_argument(
        "--docx",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="默认跟随配置文件的 enable_docx；可显式 --docx / --no-docx 覆盖",
    )
    generate.add_argument(
        "--yes",
        action="store_true",
        help="跳过调用 API 前的确认（自动化脚本使用）",
    )

    run = subparsers.add_parser("run", help="运行已有 LessonTask JSON 文件")
    run.add_argument("--task", type=Path, required=True)
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    run.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    run.add_argument(
        "--run-id",
        default=None,
        help="可选；省略时自动生成 时间-科目-年级-课题-后缀",
    )
    run.add_argument(
        "--docx",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="默认跟随配置文件的 enable_docx；可显式 --docx / --no-docx 覆盖",
    )

    inspect = subparsers.add_parser("inspect", help="查看 run_result.json 摘要")
    inspect.add_argument("--result", type=Path, required=True)

    analyze = subparsers.add_parser(
        "analyze", help="离线统计 artifacts 中的历史运行与评分（不调用模型）"
    )
    analyze.add_argument("--artifacts", type=Path, default=DEFAULT_OUTPUT)

    process = subparsers.add_parser(
        "export-process", help="将一个历史运行离线导出为完整 Markdown 过程报告"
    )
    process.add_argument("--run-dir", type=Path, required=True)
    process.add_argument("--output", type=Path, default=None)
    process.add_argument(
        "--summary-only",
        action="store_true",
        help="不嵌入每个事件的完整输入输出 JSON",
    )

    check = subparsers.add_parser(
        "check", help="检查本地配置，不发送模型请求"
    )
    check.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser


def _read_task(path: Path) -> LessonTask:
    return LessonTask.model_validate_json(path.read_text(encoding="utf-8"))


def _read_config(path: Path) -> ExperimentConfig:
    return ExperimentConfig.model_validate_json(path.read_text(encoding="utf-8"))


def _ask(
    label: str,
    *,
    required: bool = False,
    default: str | None = None,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> str:
    while True:
        if required:
            hint = " [必填]"
        elif default is not None:
            hint = f" [默认：{default}]"
        else:
            hint = " [可选，回车跳过]"
        value = input_fn(f"{label}{hint}：").strip()
        if value:
            return value
        if default is not None:
            return default
        if not required:
            return ""
        output_fn("  该字段必须填写，请重新输入。")


def _ask_int(
    label: str,
    *,
    default: int | None = None,
    minimum: int = 1,
    maximum: int = 240,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int | None:
    while True:
        raw = _ask(
            label,
            default=str(default) if default is not None else None,
            input_fn=input_fn,
            output_fn=output_fn,
        )
        if not raw:
            return None
        try:
            value = int(raw)
        except ValueError:
            output_fn("  请输入整数。")
            continue
        if minimum <= value <= maximum:
            return value
        output_fn(f"  请输入 {minimum} 到 {maximum} 之间的整数。")


def _split_list(raw: str) -> list[str]:
    """Use Chinese or English semicolons without splitting natural commas."""

    return [item.strip() for item in re.split(r"[;；]", raw) if item.strip()]


def _choose_style(
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> str:
    choices = {
        "1": "choose_the_best_fit_for_this_topic",
        "2": "inquiry_through_cognitive_conflict",
        "3": "authentic_problem_driven",
        "4": "dialogue_and_discussion",
        "5": "project_or_task_based",
        "6": "close_reading_and_evidence",
    }
    output_fn("\n课堂风格（直接回车让模型按课题选择）：")
    output_fn("  1. 模型按课题选择（默认）")
    output_fn("  2. 认知冲突与探究")
    output_fn("  3. 真实问题驱动")
    output_fn("  4. 对话与讨论")
    output_fn("  5. 项目/任务驱动")
    output_fn("  6. 文本细读与证据")
    while True:
        raw = input_fn("请选择 1–6 [默认：1]：").strip() or "1"
        if raw in choices:
            return choices[raw]
        output_fn("  请输入 1 到 6。")


def collect_interactive_task(
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    preset_run_name: str | None = None,
) -> tuple[LessonTask, str]:
    """Collect a useful task with only three truly required questions."""

    output_fn("\n=== Paper#4 交互式教案生成 ===")
    output_fn("标注 [必填] 的字段必须输入；可选字段直接按 Enter 跳过。")
    output_fn("列表字段如有多项，请使用中文或英文分号分隔。\n")
    output_fn("--- 必填信息 ---")

    subject = _ask(
        "科目", required=True, input_fn=input_fn, output_fn=output_fn
    )
    grade = _ask(
        "年级", required=True, input_fn=input_fn, output_fn=output_fn
    )
    topic = _ask(
        "课题", required=True, input_fn=input_fn, output_fn=output_fn
    )
    output_fn("\n--- 可选信息（直接按 Enter 即可采用默认值或跳过）---")
    duration = _ask_int(
        "课时长度（分钟）",
        default=45,
        minimum=5,
        maximum=240,
        input_fn=input_fn,
        output_fn=output_fn,
    )
    assert duration is not None
    default_course = f"{grade}{subject}《{topic}》，{duration}分钟"
    course_information = _ask(
        "课程说明",
        default=default_course,
        input_fn=input_fn,
        output_fn=output_fn,
    )
    textbook_version = _ask(
        "教材版本",
        input_fn=input_fn,
        output_fn=output_fn,
    )
    textbook_content = _ask(
        "教材内容或本课内容摘要",
        input_fn=input_fn,
        output_fn=output_fn,
    )
    standards = _split_list(
        _ask(
            "课程标准（多项用分号分隔）",
            input_fn=input_fn,
            output_fn=output_fn,
        )
    )
    objectives = _split_list(
        _ask(
            "希望达成的学习目标（多项用分号分隔）",
            input_fn=input_fn,
            output_fn=output_fn,
        )
    )
    student_profile = _ask(
        "学情说明",
        input_fn=input_fn,
        output_fn=output_fn,
    )
    class_size = _ask_int(
        "班级人数",
        default=None,
        minimum=1,
        maximum=200,
        input_fn=input_fn,
        output_fn=output_fn,
    )
    resources = _split_list(
        _ask(
            "可用教学资源（多项用分号分隔）",
            input_fn=input_fn,
            output_fn=output_fn,
        )
    )
    additional_requirements = _ask(
        "其他要求（例如必须包含实验、不能分组）",
        input_fn=input_fn,
        output_fn=output_fn,
    )
    lesson_style = _choose_style(input_fn=input_fn, output_fn=output_fn)
    detail_level = _ask(
        "详细程度：standard 或 showcase",
        default="showcase",
        input_fn=input_fn,
        output_fn=output_fn,
    ).lower()
    if detail_level not in {"standard", "showcase"}:
        output_fn("  未识别详细程度，已采用 showcase。")
        detail_level = "showcase"

    if preset_run_name is None:
        run_name = _ask(
            "本次运行短名称",
            input_fn=input_fn,
            output_fn=output_fn,
        )
    else:
        run_name = preset_run_name

    constraints: dict[str, object] = {"must_include_student_activity": True}
    if class_size is not None:
        constraints["class_size"] = class_size
    if additional_requirements:
        constraints["additional_requirements"] = additional_requirements

    task = LessonTask(
        task_id=automatic_task_id(subject, grade, topic),
        mode="generate",
        language="zh",
        subject=subject,
        grade=grade,
        topic=topic,
        duration_minutes=duration,
        course_information=course_information,
        textbook_content=textbook_content,
        curriculum_standards=standards,
        learning_objectives=objectives,
        student_profile=student_profile,
        class_constraints=constraints,
        available_resources=resources,
        required_sections=[
            "content_analysis",
            "student_analysis",
            "learning_objectives",
            "key_points",
            "difficult_points",
            "procedure_steps",
            "assessment_plan",
            "differentiation",
            "homework",
            "board_design",
        ],
        source_refs=["interactive_cli:user_input"],
        metadata={
            "input_method": "interactive_cli_v1",
            "textbook_version": textbook_version,
            "detail_level": detail_level,
            "creative_intensity": "high_but_grounded",
            "lesson_style": lesson_style,
            "review_status": "pending_teacher_review",
        },
    )
    return task, run_name


def _confirm(
    prompt: str,
    *,
    input_fn: Callable[[str], str] = input,
) -> bool:
    raw = input_fn(f"{prompt} [Y/n]：").strip().lower()
    return raw in {"", "y", "yes", "是"}


def _print_task_summary(
    task: LessonTask,
    run_id: str,
    input_path: Path,
    *,
    output_fn: Callable[[str], None] = print,
) -> None:
    output_fn("\n=== 输入摘要 ===")
    output_fn(f"科目/年级/课题：{task.subject} / {task.grade} / {task.topic}")
    output_fn(f"课时：{task.duration_minutes} 分钟")
    output_fn(
        f"学习目标：{len(task.learning_objectives)} 条"
        "（0 条时由 Design Architect 与 Writer 共同设计）"
    )
    output_fn(f"课程标准：{len(task.curriculum_standards)} 条")
    evidence = build_task_evidence_profile(task)
    output_fn(f"证据完整度：{evidence['readiness_level']}")
    for limitation in evidence["limitations"]:
        output_fn(f"  注意：{limitation}")
    output_fn(f"运行目录名：{run_id}")
    output_fn(f"输入已保存：{input_path}")


def _print_result(result: object) -> None:
    payload = {
        "run_id": result.run_id,
        "status": result.status.value,
        "stop_reason": result.stop_reason.value if result.stop_reason else None,
        "best_version_id": result.best_version_id,
        "last_version_id": result.last_version_id,
        "model_call_count": result.model_call_count,
        "token_usage": result.token_usage.model_dump(mode="json"),
        "estimated_cost": result.estimated_cost,
        "artifact_dir": str(Path(result.trace_path).parent),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _run_interactive(args: argparse.Namespace) -> int:
    try:
        task, entered_run_name = collect_interactive_task(
            preset_run_name=args.run_name
        )
    except (EOFError, KeyboardInterrupt):
        print("\n已取消，未调用模型。")
        return 130
    run_id = automatic_run_id(task, label=entered_run_name)
    output_root = args.output.resolve()
    run_dir = output_root / run_id
    input_path = run_dir / "input_task.json"
    atomic_write_text(
        input_path,
        json.dumps(
            task.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        + "\n",
    )
    _print_task_summary(task, run_id, input_path)
    if not args.yes and not _confirm("以上信息是否正确并开始真实 API 生成？"):
        print(f"已取消 API 调用。输入仍保存在：{input_path}")
        return 0
    result = PipelineService(output_root).run(
        task,
        _read_config(args.config),
        run_id=run_id,
        include_docx=args.docx,
    )
    _print_result(result)
    return 1 if result.status.value == "failed" else 0


def _check_configuration(path: Path) -> int:
    config = _read_config(path)
    profiles = default_profile_registry(config.role_model_configs)
    summaries = {
        profile_id: OpenAICompatibleProvider(profile.model).configuration_summary()
        for profile_id, profile in profiles.items()
        if profile_id in config.role_model_configs
    }
    ok = all(item["api_key_present"] for item in summaries.values())
    print(
        json.dumps(
            {
                "status": "ok" if ok else "error",
                "execution_mode": config.execution_mode,
                "config": str(path.resolve()),
                "profiles": summaries,
                "note": "API key values are never displayed; no model was called.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "generate":
        return _run_interactive(args)
    if args.command == "check":
        return _check_configuration(args.config)
    if args.command == "run":
        result = PipelineService(args.output).run(
            _read_task(args.task),
            _read_config(args.config),
            run_id=args.run_id,
            include_docx=args.docx,
        )
        _print_result(result)
        return 1 if result.status.value == "failed" else 0

    if args.command == "analyze":
        print(
            json.dumps(
                analyze_artifacts(args.artifacts),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "export-process":
        output = export_process_report(
            args.run_dir,
            args.output,
            include_payloads=not args.summary_only,
        )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "model_calls_made": 0,
                    "output": str(output.resolve()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    payload = json.loads(args.result.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "run_id": payload["run_id"],
                "status": payload["status"],
                "stop_reason": payload.get("stop_reason"),
                "best_version_id": payload.get("best_version_id"),
                "last_version_id": payload.get("last_version_id"),
                "versions": len(payload.get("versions", [])),
                "iterations": len(payload.get("iterations", [])),
                "model_call_count": payload.get("model_call_count", 0),
                "token_usage": payload.get("token_usage", {}),
                "estimated_cost": payload.get("estimated_cost", 0),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except (OSError, UnicodeError, ValueError, KeyError) as exc:
        # Expected local/preflight failures should be actionable in Anaconda
        # Prompt instead of presenting users with an implementation traceback.
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "note": "未开始或未完成模型闭环；请修正路径、JSON、配置或 run_id 后重试。",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
