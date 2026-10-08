"""Submission coordinator for a single persistent real-model worker."""

from __future__ import annotations

import os
from concurrent.futures import Executor, ProcessPoolExecutor
from datetime import datetime
from multiprocessing import get_context
from pathlib import Path

from paper4_pipeline.domain.ids import stable_id
from paper4_pipeline.domain.naming import safe_name_component
from paper4_pipeline.web_api.registry import RunRecord, RunRegistry
from paper4_pipeline.web_api.runner import execute_generate, execute_optimize
from paper4_pipeline.web_api.schemas import (
    CreateRunRequest,
    EngineMode,
    RunAccepted,
)
from paper4_pipeline.web_api.settings import EngineSettings


class EngineManager:
    def __init__(
        self,
        settings: EngineSettings,
        *,
        executor: Executor | None = None,
    ) -> None:
        self.settings = settings
        self.registry = RunRegistry(settings)
        self._executor = executor
        self._owns_executor = executor is None

    def start(self) -> None:
        self.registry.recover_interrupted_runs()
        if self._executor is None:
            self._executor = ProcessPoolExecutor(
                max_workers=1,
                mp_context=get_context("spawn"),
            )

    def shutdown(self) -> None:
        if self._executor is not None and self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=False)
            self._executor = None

    def submit_generate(self, request: CreateRunRequest) -> RunAccepted:
        if request.task.mode != EngineMode.GENERATE:
            raise ValueError("generate endpoint requires task.mode=generate")
        record, created = self._create_record(request)
        if created:
            try:
                self._require_executor().submit(
                    execute_generate,
                    self.settings.worker_payload(),
                    record.engine_run_id,
                    request.task.model_dump(mode="json"),
                )
            except Exception:
                self._mark_submission_failed(record.engine_run_id)
                raise
        return _accepted(record)

    def submit_optimize(
        self,
        request: CreateRunRequest,
        incoming_path: Path,
        *,
        original_filename: str,
    ) -> RunAccepted:
        if request.task.mode != EngineMode.OPTIMIZE:
            raise ValueError("optimize endpoint requires task.mode=optimize")
        record, created = self._create_record(
            request, original_filename=original_filename
        )
        if not created:
            incoming_path.unlink(missing_ok=True)
            return _accepted(record)
        destination = self.registry.run_dir(record.engine_run_id) / "input" / "original.docx"
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(incoming_path, destination)
            self._require_executor().submit(
                execute_optimize,
                self.settings.worker_payload(),
                record.engine_run_id,
                request.task.model_dump(mode="json"),
            )
        except Exception:
            incoming_path.unlink(missing_ok=True)
            self._mark_submission_failed(record.engine_run_id)
            raise
        return _accepted(record)

    def _mark_submission_failed(self, engine_run_id: str) -> None:
        self.registry.update(
            engine_run_id,
            status="failed",
            stage="failed",
            pipeline_status="failed",
            error_code="ENGINE_WORKER_SUBMISSION_FAILED",
            error_message="任务无法提交到模型工作进程，请稍后重试",
        )

    def _create_record(
        self,
        request: CreateRunRequest,
        *,
        original_filename: str = "",
    ) -> tuple[RunRecord, bool]:
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        readable = "-".join(
            safe_name_component(item, max_length=16)
            for item in (
                request.task.subject,
                request.task.grade,
                request.task.topic,
            )
        )
        engine_run_id = (
            f"{stamp}-{readable}-{request.external_job_id[-6:].lower()}"
        )
        record = RunRecord(
            engine_run_id=engine_run_id,
            external_job_id=request.external_job_id,
            request_sha256=request.request_sha256,
            mode=request.task.mode,
            task_id=stable_id("lesson", request.external_job_id),
            subject=request.task.subject,
            grade=request.task.grade,
            topic=request.task.topic,
            original_filename=Path(original_filename).name,
        )
        return self.registry.create(record)

    def _require_executor(self) -> Executor:
        if self._executor is None:
            raise RuntimeError("engine manager has not started")
        return self._executor


def _accepted(record: RunRecord) -> RunAccepted:
    return RunAccepted(
        engine_run_id=record.engine_run_id,
        external_job_id=record.external_job_id,
        status=record.status,
        created_at=record.created_at,
    )
