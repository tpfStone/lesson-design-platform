"""Pure worker entry points that execute the existing real pipeline."""

from __future__ import annotations

import os
from pathlib import Path

from paper4_pipeline.domain.ids import stable_id
from paper4_pipeline.domain.models import (
    ExperimentConfig,
    LessonPlanDocument,
    LessonTask,
    PipelineResult,
    RunStatus,
    TaskMode,
)
from paper4_pipeline.exporters.common import atomic_write_text
from paper4_pipeline.service import PipelineService
from paper4_pipeline.web_api.docx_ingestion import DocxIngestionError, extract_docx
from paper4_pipeline.web_api.generated_docx import restore_generated_docx
from paper4_pipeline.web_api.normalizer import DocxNormalizer
from paper4_pipeline.web_api.registry import RunRegistry
from paper4_pipeline.web_api.schemas import EngineLessonInput, EngineRunStatus
from paper4_pipeline.web_api.settings import EngineSettings


REQUIRED_SECTIONS = [
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
]


def load_config(settings: EngineSettings) -> ExperimentConfig:
    return ExperimentConfig.model_validate_json(
        settings.config_path.read_text(encoding="utf-8")
    )


def build_task(
    task_input: EngineLessonInput,
    *,
    task_id: str,
    initial_plan: object | None = None,
    source_sha256: str = "",
) -> LessonTask:
    constraints: dict[str, object] = {"must_include_student_activity": True}
    if task_input.class_size is not None:
        constraints["class_size"] = task_input.class_size
    if task_input.optimization_focus:
        constraints["optimization_focus"] = task_input.optimization_focus
    if task_input.must_preserve_content:
        constraints["must_preserve_content"] = task_input.must_preserve_content
    course = task_input.course_information.strip() or (
        f"{task_input.grade}{task_input.subject}《{task_input.topic}》，"
        f"{task_input.duration_minutes}分钟"
    )
    return LessonTask(
        task_id=task_id,
        mode=(
            TaskMode.GENERATE
            if task_input.mode.value == "generate"
            else TaskMode.OPTIMIZE
        ),
        subject=task_input.subject,
        grade=task_input.grade,
        topic=task_input.topic,
        duration_minutes=task_input.duration_minutes,
        course_information=course,
        textbook_content=task_input.textbook_content,
        curriculum_standards=task_input.curriculum_standards,
        learning_objectives=task_input.learning_objectives,
        student_profile=task_input.student_profile,
        class_constraints=constraints,
        available_resources=task_input.available_resources,
        required_sections=REQUIRED_SECTIONS,
        source_refs=[
            "web:user_input",
            *([f"web:docx:{source_sha256}"] if source_sha256 else []),
        ],
        initial_plan=initial_plan,
        metadata={
            "input_method": "web_v1",
            "lesson_style": task_input.lesson_style,
            "detail_level": task_input.detail_level,
            "creative_intensity": "high_but_grounded",
            "review_status": "pending_teacher_review",
            "textbook_version": (
                task_input.textbook_version
                or (
                    initial_plan.metadata.textbook_version
                    if isinstance(initial_plan, LessonPlanDocument) else ""
                )
            ),
            "additional_requirements": task_input.additional_requirements,
        },
    )


def execute_generate(
    settings_payload: dict[str, object],
    engine_run_id: str,
    task_payload: dict[str, object],
) -> None:
    settings = EngineSettings.from_worker_payload(settings_payload)
    registry = RunRegistry(settings)
    task_input = EngineLessonInput.model_validate(task_payload)
    record = registry.get(engine_run_id)
    try:
        registry.update(
            engine_run_id, status=EngineRunStatus.RUNNING, stage="design_architect"
        )
        task = build_task(task_input, task_id=record.task_id)
        _run_pipeline(settings, registry, engine_run_id, task)
    except Exception as exc:
        _fail(registry, engine_run_id, exc)


def execute_optimize(
    settings_payload: dict[str, object],
    engine_run_id: str,
    task_payload: dict[str, object],
) -> None:
    settings = EngineSettings.from_worker_payload(settings_payload)
    registry = RunRegistry(settings)
    task_input = EngineLessonInput.model_validate(task_payload)
    record = registry.get(engine_run_id)
    source_path = registry.run_dir(engine_run_id) / "input" / "original.docx"
    try:
        registry.update(
            engine_run_id,
            status=EngineRunStatus.PREPROCESSING,
            stage="docx_security_check",
        )
        raw = extract_docx(
            source_path,
            original_filename=record.original_filename,
            settings=settings,
        )
        atomic_write_text(
            registry.run_dir(engine_run_id) / "normalized" / "raw_document.json",
            raw.model_dump_json(indent=2) + "\n",
        )
        registry.update(
            engine_run_id,
            stage="docx_normalize",
            source_sha256=raw.source_sha256,
            parse_warnings=raw.warnings,
        )
        config = load_config(settings)
        plan_id = stable_id("plan", record.task_id, raw.source_sha256)
        normalized = restore_generated_docx(
            raw, task_input, task_id=record.task_id, plan_id=plan_id,
            artifacts_root=settings.artifacts_root,
        )
        if normalized is None:
            from paper4_pipeline.observability.call_ledger import activate_call_ledger

            with activate_call_ledger(
                registry.run_dir(engine_run_id) / "normalized" / "model_call_ledger.jsonl"
            ):
                normalized = DocxNormalizer(config).normalize(
                    raw, task_input, task_id=record.task_id, plan_id=plan_id,
                )
        atomic_write_text(
            registry.run_dir(engine_run_id)
            / "normalized"
            / "initial_plan.json",
            normalized.model_dump_json(indent=2) + "\n",
        )
        registry.update(
            engine_run_id,
            status=EngineRunStatus.RUNNING,
            stage="judge",
            parse_warnings=normalized.warnings,
            preprocessing_model_call_count=int(
                1 if normalized.model_metadata.get("attempts") is None
                else normalized.model_metadata["attempts"]
            ),
            preprocessing_input_tokens=normalized.usage.input_tokens,
            preprocessing_output_tokens=normalized.usage.output_tokens,
            preprocessing_estimated_cost=normalized.estimated_cost,
        )
        task = build_task(
            task_input,
            task_id=record.task_id,
            initial_plan=normalized.lesson_plan,
            source_sha256=raw.source_sha256,
        )
        _run_pipeline(settings, registry, engine_run_id, task, config=config)
    except Exception as exc:
        _fail(registry, engine_run_id, exc)


def _run_pipeline(
    settings: EngineSettings,
    registry: RunRegistry,
    engine_run_id: str,
    task: LessonTask,
    *,
    config: ExperimentConfig | None = None,
) -> None:
    effective_config = config or load_config(settings)
    result = PipelineService(settings.artifacts_root).run(
        task,
        effective_config,
        run_id=engine_run_id,
        include_docx=True,
    )
    status = {
        RunStatus.COMPLETED: EngineRunStatus.COMPLETED,
        RunStatus.NEEDS_HUMAN: EngineRunStatus.NEEDS_HUMAN,
        RunStatus.FAILED: EngineRunStatus.FAILED,
    }[result.status]
    errors = [str(item) for item in result.errors]
    registry.update(
        engine_run_id,
        status=status,
        stage="finalize",
        pipeline_status=result.status.value,
        stop_reason=result.stop_reason.value if result.stop_reason else None,
        best_version_id=result.best_version_id or None,
        last_version_id=result.last_version_id or None,
        error_code="PIPELINE_FAILED" if status == EngineRunStatus.FAILED else "",
        error_message=_public_message(errors[-1]) if errors else "",
    )


def _fail(registry: RunRegistry, engine_run_id: str, exc: Exception) -> None:
    code = _classify_error(exc)
    changes: dict[str, object] = {
        "status": EngineRunStatus.FAILED,
        "stage": "failed",
        "pipeline_status": "failed",
        "error_code": code,
        "error_message": _public_message(str(exc), code=code),
        "internal_error_detail": _redacted_error_detail(exc),
    }
    usage = getattr(exc, "usage", None)
    if usage is not None:
        changes.update(
            preprocessing_model_call_count=max(
                int(getattr(exc, "attempts", 0)), 0
            ),
            preprocessing_input_tokens=max(
                int(getattr(usage, "input_tokens", 0)), 0
            ),
            preprocessing_output_tokens=max(
                int(getattr(usage, "output_tokens", 0)), 0
            ),
            preprocessing_estimated_cost=max(
                float(getattr(exc, "estimated_cost", 0)), 0
            ),
        )
    registry.update(
        engine_run_id,
        **changes,
    )


def _redacted_error_detail(exc: Exception) -> str:
    """Keep the diagnostic locally without exposing it in the public API."""
    detail = f"{type(exc).__name__}: {exc}"
    for name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        secret = os.getenv(name, "").strip()
        if secret:
            detail = detail.replace(secret, "[REDACTED]")
    return detail[:2000]


def _classify_error(exc: Exception) -> str:
    if isinstance(exc, DocxIngestionError):
        return exc.code
    text = f"{type(exc).__name__}: {exc}".lower()
    if "402" in text or "payment required" in text or "insufficient balance" in text:
        return "MODEL_BALANCE_EXHAUSTED"
    if "401" in text or "authentication" in text or "api key" in text:
        return "MODEL_AUTH_FAILED"
    if "429" in text or "rate limit" in text:
        return "MODEL_RATE_LIMITED"
    if "timeout" in text or "connection" in text or "503" in text or "502" in text:
        return "MODEL_UNAVAILABLE"
    is_docx_normalization = any(name in text for name in (
        "docx_normalizer", "docx_overview", "docx_activities", "normalizer",
    ))
    if is_docx_normalization and (
        "lengthfinishreasonerror" in text or "length limit was reached" in text
    ):
        return "DOCX_NORMALIZATION_TOO_LARGE"
    if is_docx_normalization:
        return "DOCX_NORMALIZATION_FAILED"
    return "ENGINE_INTERNAL_ERROR"


def _public_message(message: str, *, code: str = "") -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    safe = message.replace(api_key, "[REDACTED]") if api_key else message
    known = {
        "MODEL_BALANCE_EXHAUSTED": "模型账户余额不足，请充值后创建新的重试任务",
        "MODEL_AUTH_FAILED": "模型鉴权失败，请管理员检查服务端 API Key",
        "MODEL_RATE_LIMITED": "模型请求过于频繁，请稍后创建新的重试任务",
        "MODEL_UNAVAILABLE": "模型服务暂时不可用，请稍后重试",
        "DOCX_NORMALIZATION_FAILED": (
            "Word 已成功读取，但转换为内部教案结构时未通过校验；"
            "请勿反复提交同一文件，可联系管理员查看具体错误"
        ),
        "DOCX_NORMALIZATION_TOO_LARGE": (
            "Word 已成功读取，但结构化服务的输出被截断；本次未进入教案改写。"
            "请联系管理员检查导入日志，勿反复提交相同文件"
        ),
    }
    return known.get(code, safe[:800] or "引擎执行失败")
