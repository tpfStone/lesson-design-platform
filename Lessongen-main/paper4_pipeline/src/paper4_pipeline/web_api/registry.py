"""Small file-backed run registry used across the API and worker process."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from pydantic import Field

from paper4_pipeline.domain.models import PipelineResult, RunStatus, StrictModel
from paper4_pipeline.exporters.common import atomic_write_text
from paper4_pipeline.web_api.schemas import EngineMode, EngineRunStatus
from paper4_pipeline.web_api.settings import EngineSettings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunRecord(StrictModel):
    schema_version: str = "paper4-web-run-v0.1"
    engine_run_id: str
    external_job_id: str
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mode: EngineMode
    task_id: str
    subject: str
    grade: str
    topic: str
    status: EngineRunStatus = EngineRunStatus.QUEUED
    stage: str = "queued"
    original_filename: str = ""
    source_sha256: str = ""
    pipeline_status: str | None = None
    stop_reason: str | None = None
    best_version_id: str | None = None
    last_version_id: str | None = None
    error_code: str = ""
    error_message: str = ""
    internal_error_detail: str = ""
    parse_warnings: list[str] = Field(default_factory=list)
    preprocessing_model_call_count: int = Field(default=0, ge=0)
    preprocessing_input_tokens: int = Field(default=0, ge=0)
    preprocessing_output_tokens: int = Field(default=0, ge=0)
    preprocessing_estimated_cost: float = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RunRegistry:
    def __init__(self, settings: EngineSettings) -> None:
        self.settings = settings
        self.runs_root = settings.state_root / "runs"
        self.incoming_root = settings.state_root / "incoming"
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.incoming_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def run_dir(self, engine_run_id: str) -> Path:
        if not engine_run_id or any(char in engine_run_id for char in "/\\"):
            raise ValueError("invalid engine_run_id")
        path = (self.runs_root / engine_run_id).resolve()
        if self.runs_root.resolve() not in path.parents:
            raise ValueError("run path escaped state root")
        return path

    def record_path(self, engine_run_id: str) -> Path:
        return self.run_dir(engine_run_id) / "web_run.json"

    def _event_path(self, engine_run_id: str) -> Path:
        return self.run_dir(engine_run_id) / "lifecycle_events.jsonl"

    def find_by_external_job_id(self, external_job_id: str) -> RunRecord | None:
        for path in self.runs_root.glob("*/web_run.json"):
            try:
                record = RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if record.external_job_id == external_job_id:
                return record
        return None

    def records(self) -> list[RunRecord]:
        result: list[RunRecord] = []
        for path in self.runs_root.glob("*/web_run.json"):
            try:
                result.append(
                    RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
                )
            except Exception:
                continue
        return result

    def recover_interrupted_runs(self) -> int:
        """Reconcile durable results first; never invent success after process loss."""
        active = {
            EngineRunStatus.QUEUED,
            EngineRunStatus.PREPROCESSING,
            EngineRunStatus.RUNNING,
            EngineRunStatus.EXPORTING,
        }
        recovered = 0
        for record in self.records():
            if record.status not in active:
                continue
            result_path = self.settings.artifacts_root / record.engine_run_id / "run_result.json"
            result: PipelineResult | None = None
            if result_path.is_file():
                try:
                    result = PipelineResult.model_validate_json(
                        result_path.read_text(encoding="utf-8")
                    )
                except Exception:
                    # A partial/corrupt result is not evidence of success.
                    result = None
            if result is not None:
                terminal = {
                    RunStatus.COMPLETED: EngineRunStatus.COMPLETED,
                    RunStatus.NEEDS_HUMAN: EngineRunStatus.NEEDS_HUMAN,
                    RunStatus.FAILED: EngineRunStatus.FAILED,
                }[result.status]
                self.update(
                    record.engine_run_id,
                    status=terminal,
                    stage="finalize",
                    pipeline_status=result.status.value,
                    stop_reason=(
                        result.stop_reason.value if result.stop_reason else None
                    ),
                    best_version_id=result.best_version_id or None,
                    last_version_id=result.last_version_id or None,
                    error_code=("PIPELINE_FAILED" if terminal == EngineRunStatus.FAILED else ""),
                    error_message=(
                        "引擎在重启前记录了失败结果，请查看可用恢复产物"
                        if terminal == EngineRunStatus.FAILED
                        else ""
                    ),
                )
                recovered += 1
                continue
            self.update(
                record.engine_run_id,
                status=EngineRunStatus.FAILED,
                stage="failed",
                pipeline_status="failed",
                error_code="ENGINE_RESTART_INTERRUPTED",
                error_message="引擎重启中断了任务，请创建新的重试任务",
            )
            recovered += 1
        return recovered

    def create(self, record: RunRecord) -> tuple[RunRecord, bool]:
        with self._lock:
            existing = self.find_by_external_job_id(record.external_job_id)
            if existing:
                if existing.request_sha256 != record.request_sha256:
                    raise ValueError("ENGINE_IDEMPOTENCY_CONFLICT")
                return existing, False
            directory = self.run_dir(record.engine_run_id)
            directory.mkdir(parents=True, exist_ok=False)
            self._write(record)
            self._append_lifecycle(record)
            return record, True

    def get(self, engine_run_id: str) -> RunRecord:
        path = self.record_path(engine_run_id)
        if not path.is_file():
            raise KeyError(engine_run_id)
        return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def update(self, engine_run_id: str, **changes: object) -> RunRecord:
        with self._lock:
            previous = self.get(engine_run_id)
            record = previous.model_copy(update={**changes, "updated_at": utc_now()})
            record = RunRecord.model_validate(record.model_dump(mode="python"))
            self._write(record)
            if record.status != previous.status or record.stage != previous.stage:
                self._append_lifecycle(record)
            return record

    def _write(self, record: RunRecord) -> None:
        atomic_write_text(
            self.record_path(record.engine_run_id),
            record.model_dump_json(indent=2) + "\n",
        )

    def _append_lifecycle(self, record: RunRecord) -> None:
        path = self._event_path(record.engine_run_id)
        terminal = record.status in {
            EngineRunStatus.COMPLETED,
            EngineRunStatus.NEEDS_HUMAN,
            EngineRunStatus.FAILED,
        }
        existing = self.lifecycle_events(record.engine_run_id)
        nonterminal_sequences = [
            int(item.get("sequence") or 0)
            for item in existing
            if int(item.get("sequence") or 0) < 1_000_000
        ]
        payload = {
            # Keep lifecycle events strictly increasing. Pipeline trace events occupy the
            # 1000+ range in the projection; the single terminal event sorts last.
            "sequence": (
                1_000_000
                if terminal
                else max(nonterminal_sequences, default=0) + 1
            ),
            "event_type": (
                "run.terminal"
                if terminal
                else "run.lifecycle"
            ),
            "stage": record.stage,
            "round_index": 0,
            "version_id": record.last_version_id or "",
            "message": _lifecycle_message(record),
            "occurred_at": record.updated_at.isoformat(),
        }
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def lifecycle_events(self, engine_run_id: str) -> list[dict[str, object]]:
        path = self._event_path(engine_run_id)
        if not path.is_file():
            return []
        result: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                result.append(json.loads(line))
        return result


def _lifecycle_message(record: RunRecord) -> str:
    messages = {
        EngineRunStatus.QUEUED: "任务已进入真实模型队列",
        EngineRunStatus.PREPROCESSING: "正在安全读取并结构化原教案",
        EngineRunStatus.RUNNING: "多智能体教案流程正在运行",
        EngineRunStatus.EXPORTING: "正在生成结果文件",
        EngineRunStatus.COMPLETED: "教案闭环已完成",
        EngineRunStatus.NEEDS_HUMAN: "已形成最佳版本，建议教师复核",
        EngineRunStatus.FAILED: record.error_message or "任务执行失败",
    }
    return messages[record.status]
