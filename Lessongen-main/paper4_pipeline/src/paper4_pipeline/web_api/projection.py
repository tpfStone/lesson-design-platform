"""Safe public projections over trace, result and artifact files."""

from __future__ import annotations

import json
from pathlib import Path

from paper4_pipeline.domain.models import CritiqueStatus, PipelineResult
from paper4_pipeline.control.optimization import optimization_summary
from paper4_pipeline.web_api.docx_ingestion import sha256_file
from paper4_pipeline.web_api.registry import RunRecord, RunRegistry
from paper4_pipeline.web_api.schemas import (
    EngineArtifact,
    EngineError,
    EngineEventPage,
    EngineResult,
    EngineRunStatus,
    EngineUsage,
    ImplementedChangeSummary,
    PublicEngineEvent,
    ReviewSummary,
    RunSnapshot,
)
from paper4_pipeline.web_api.settings import EngineSettings


_STAGE_PROGRESS = {
    "run": 5,
    "bootstrap": 8,
    "design_architect": 14,
    "writer": 27,
    "judge": 36,
    "evaluation_router": 39,
    "critics": 52,
    "critique_aggregator": 58,
    "validator": 65,
    "validation_router": 68,
    "rewriter": 80,
    "verifier": 87,
    "finalize": 92,
}

_STAGE_MESSAGES = {
    "run": "正在初始化任务",
    "bootstrap": "正在检查任务约束",
    "design_architect": "正在比较教学设计路线",
    "writer": "正在形成教案版本",
    "judge": "正在进行八维内部质量检查",
    "evaluation_router": "正在判断下一步处理路线",
    "critics": "学科、教学法与对齐角色正在独立审阅",
    "critique_aggregator": "正在汇总三类审阅意见",
    "validator": "正在去重并判断意见是否可执行",
    "validation_router": "正在形成有效修改清单",
    "rewriter": "正在按有效意见进行最小必要修改",
    "verifier": "正在核对修改是否真正落实",
    "finalize": "正在选择最佳版本并整理产物",
}

_TERMINAL = {
    EngineRunStatus.COMPLETED,
    EngineRunStatus.NEEDS_HUMAN,
    EngineRunStatus.FAILED,
}


class EngineProjection:
    def __init__(self, settings: EngineSettings) -> None:
        self.settings = settings
        self.registry = RunRegistry(settings)

    def snapshot(self, engine_run_id: str) -> RunSnapshot:
        record = self.registry.get(engine_run_id)
        trace = self._trace_rows(engine_run_id)
        latest = trace[-1] if trace else None
        stage = str(latest.get("stage")) if latest else record.stage
        round_index = int(latest.get("round_index") or 0) if latest else 0
        version_id = str(latest.get("version_id") or "") if latest else ""
        usage = self._usage(engine_run_id, trace)
        events = self._events(engine_run_id)
        return RunSnapshot(
            engine_run_id=record.engine_run_id,
            external_job_id=record.external_job_id,
            status=record.status,
            stage=stage,
            round_index=round_index,
            version_id=version_id or record.last_version_id or "",
            progress_percent=(100 if record.status in _TERMINAL else _progress(stage)),
            pipeline_status=record.pipeline_status,
            stop_reason=record.stop_reason,
            best_version_id=record.best_version_id,
            last_version_id=record.last_version_id,
            usage=usage,
            last_event_sequence=max((item.sequence for item in events), default=0),
            error=(
                EngineError(code=record.error_code, message=record.error_message)
                if record.error_code
                else None
            ),
            updated_at=record.updated_at,
        )

    def events(
        self, engine_run_id: str, *, after_sequence: int = 0, limit: int = 100
    ) -> EngineEventPage:
        all_events = [
            item for item in self._events(engine_run_id) if item.sequence > after_sequence
        ]
        page = all_events[:limit]
        return EngineEventPage(
            items=page,
            last_sequence=page[-1].sequence if page else after_sequence,
            has_more=len(all_events) > limit,
        )

    def result(self, engine_run_id: str) -> EngineResult:
        record = self.registry.get(engine_run_id)
        result = self._pipeline_result(engine_run_id)
        if result is None or not result.versions:
            raise RuntimeError("ENGINE_RESULT_NOT_READY")
        by_id = {item.version_id: item for item in result.versions}
        best = by_id[result.best_version_id]
        evaluation = best.internal_evaluation
        changes: list[ImplementedChangeSummary] = []
        for rewrite in result.rewrite_records:
            for change in rewrite.changes:
                changes.append(
                    ImplementedChangeSummary(
                        critique_id=change.critique_id,
                        target_path=change.target_path,
                        summary=change.after_summary or change.before_summary,
                    )
                )
        unresolved = [
            item.issue
            for item in result.critiques
            if item.status
            not in {CritiqueStatus.IMPLEMENTED, CritiqueStatus.VERIFIED_FIXED}
        ]
        trace = self._trace_rows(engine_run_id)
        reviewed_roles = list(dict.fromkeys(
            str(row.get("actor_profile_id"))
            for row in trace
            if row.get("event_type") == "critic_completed"
            and row.get("actor_profile_id")
        ))
        run_start = next((row for row in trace if row.get("event_type") == "run_started"), {})
        start_summary = run_start.get("input_summary") or {}
        run_config = start_summary.get("experiment_config") or {}
        policy = run_config.get("generation_review_policy", "legacy_unknown")
        expected_roles = set(run_config.get("critic_profile_ids") or [
            "subject_critic_v0_1", "pedagogy_critic_v0_1", "alignment_critic_v0_1",
        ])
        reviews_by_round: dict[int, set[str]] = {}
        for row in trace:
            if row.get("event_type") == "critic_completed" and row.get("actor_profile_id"):
                round_index = int(row.get("round_index") or 0)
                reviews_by_round.setdefault(round_index, set()).add(
                    str(row["actor_profile_id"])
                )
        independently_reviewed = any(
            expected_roles.issubset(reviews_by_round.get(batch.round_index, set()))
            for batch in result.validation_batches
        )
        initial_version = min(result.versions, key=lambda item: (item.iteration, item.version_id))
        review = ReviewSummary(
            policy=policy,
            reviewed_roles=reviewed_roles,
            validator_completed=bool(result.validation_batches),
            independent_review_complete=independently_reviewed,
            content_changed=(initial_version.document_hash != best.document_hash),
        )
        return EngineResult(
            engine_run_id=engine_run_id,
            external_job_id=record.external_job_id,
            pipeline_status=result.status.value,
            stop_reason=result.stop_reason.value if result.stop_reason else None,
            best_version_id=result.best_version_id,
            last_version_id=result.last_version_id,
            best_lesson_plan=best.document,
            rubric_scores=evaluation.rubric_scores if evaluation else None,
            overall_score=evaluation.overall_score if evaluation else None,
            optimization=(optimization_summary(result) if record.mode.value == "optimize" else None),
            review=review,
            implemented_changes=changes,
            unresolved_issues=unresolved,
            parse_warnings=record.parse_warnings,
            artifacts=self.artifacts(engine_run_id),
        )

    def artifacts(self, engine_run_id: str) -> list[EngineArtifact]:
        record = self.registry.get(engine_run_id)
        result = self._pipeline_result(engine_run_id)
        items: list[EngineArtifact] = []
        if result and result.artifacts:
            for item in result.artifacts.artifacts:
                path = Path(item.path)
                if item.status == "ok" and not path.is_file():
                    # A listed artifact whose file is gone must not be advertised
                    # for download: Java would fetch it and treat the 404 as a
                    # transient sync failure, leaving the job stuck in "running".
                    continue
                items.append(
                    EngineArtifact(
                        artifact_id=item.artifact_id,
                        format=item.format,
                        display_name=path.name,
                        media_type=_media_type(item.format),
                        size_bytes=path.stat().st_size if path.is_file() else 0,
                        sha256=item.sha256,
                        status=item.status,
                        error=item.error,
                    )
                )
        artifact_dir = self._artifact_dir(engine_run_id)
        for artifact_id, filename, fmt in (
            ("recovery-plan-json", "recovery_lesson_plan.json", "json"),
            ("optimization-report-json", "optimization_report.json", "json"),
        ):
            path = artifact_dir / filename
            if path.is_file() and not any(x.artifact_id == artifact_id for x in items):
                items.append(_artifact(artifact_id, path, fmt))
        if record.mode.value == "optimize":
            source = self.registry.run_dir(engine_run_id) / "input" / "original.docx"
            normalized = (
                self.registry.run_dir(engine_run_id)
                / "normalized"
                / "initial_plan.json"
            )
            if source.is_file():
                items.append(_artifact("original-docx", source, "docx"))
            if normalized.is_file():
                items.append(_artifact("normalized-input-json", normalized, "json"))
        return items

    def artifact_path(self, engine_run_id: str, artifact_id: str) -> Path:
        allowed = {item.artifact_id for item in self.artifacts(engine_run_id)}
        if artifact_id not in allowed:
            raise KeyError(artifact_id)
        special = {
            "original-docx": self.registry.run_dir(engine_run_id)
            / "input"
            / "original.docx",
            "normalized-input-json": self.registry.run_dir(engine_run_id)
            / "normalized"
            / "initial_plan.json",
            "recovery-plan-json": self._artifact_dir(engine_run_id)
            / "recovery_lesson_plan.json",
            "optimization-report-json": self._artifact_dir(engine_run_id)
            / "optimization_report.json",
        }
        result = self._pipeline_result(engine_run_id)
        if result and result.artifacts:
            for item in result.artifacts.artifacts:
                if item.artifact_id == artifact_id:
                    candidate = Path(item.path).resolve()
                    root = self._artifact_dir(engine_run_id).resolve()
                    if candidate != root and root not in candidate.parents:
                        raise RuntimeError("artifact escaped run directory")
                    if not candidate.is_file():
                        raise FileNotFoundError(candidate)
                    if item.status == "ok" and sha256_file(candidate) != item.sha256:
                        raise RuntimeError("artifact hash mismatch")
                    return candidate
        if artifact_id in special:
            return special[artifact_id].resolve()
        raise KeyError(artifact_id)

    def _events(self, engine_run_id: str) -> list[PublicEngineEvent]:
        events: list[PublicEngineEvent] = []
        for item in self.registry.lifecycle_events(engine_run_id):
            status_progress = 100 if int(item["sequence"]) >= 1_000_000 else (
                3 if int(item["sequence"]) == 1 else 8
            )
            events.append(
                PublicEngineEvent(
                    **item,
                    progress_percent=status_progress,
                )
            )
        for row in self._trace_rows(engine_run_id):
            stage = str(row.get("stage") or "run")
            events.append(
                PublicEngineEvent(
                    sequence=1000 + int(row.get("sequence") or 0),
                    event_type="pipeline.progress",
                    stage=stage,
                    round_index=int(row.get("round_index") or 0),
                    version_id=str(row.get("version_id") or ""),
                    progress_percent=_progress(stage),
                    message=_STAGE_MESSAGES.get(stage, "教案流程正在推进"),
                    occurred_at=row["timestamp"],
                )
            )
        return sorted(events, key=lambda item: item.sequence)

    def _trace_rows(self, engine_run_id: str) -> list[dict[str, object]]:
        path = self._artifact_dir(engine_run_id) / "trace.jsonl"
        if not path.is_file():
            return []
        rows: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def _pipeline_result(self, engine_run_id: str) -> PipelineResult | None:
        path = self._artifact_dir(engine_run_id) / "run_result.json"
        if not path.is_file():
            return None
        return PipelineResult.model_validate_json(path.read_text(encoding="utf-8"))

    def _usage(
        self, engine_run_id: str, rows: list[dict[str, object]]
    ) -> EngineUsage:
        record = self.registry.get(engine_run_id)
        result = self._pipeline_result(engine_run_id)
        if result:
            return EngineUsage(
                model_call_count=(
                    result.model_call_count + record.preprocessing_model_call_count
                ),
                input_tokens=(
                    result.token_usage.input_tokens + record.preprocessing_input_tokens
                ),
                output_tokens=(
                    result.token_usage.output_tokens + record.preprocessing_output_tokens
                ),
                estimated_cost=(
                    result.estimated_cost + record.preprocessing_estimated_cost
                ),
            )
        model_calls = record.preprocessing_model_call_count
        input_tokens = record.preprocessing_input_tokens
        output_tokens = record.preprocessing_output_tokens
        estimated_cost = record.preprocessing_estimated_cost
        ledger_path = self._artifact_dir(engine_run_id) / "model_call_ledger.jsonl"
        if ledger_path.is_file():
            for line in ledger_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                attempt = json.loads(line)
                model_calls += 1
                input_tokens += int(attempt.get("input_tokens") or 0)
                output_tokens += int(attempt.get("output_tokens") or 0)
                estimated_cost += float(attempt.get("estimated_cost") or 0)
            return EngineUsage(
                model_call_count=model_calls,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost=estimated_cost,
            )
        countable = {
            "design_blueprint_completed", "writer_completed", "judge_completed",
            "critic_completed", "critic_failed", "validation_completed",
            "rewrite_completed", "rewrite_aborted", "optimization_pairwise_compared",
        }
        for row in rows:
            if row.get("event_type") not in countable:
                continue
            usage = row.get("token_usage") or {}
            if isinstance(usage, dict):
                current_input = int(usage.get("input_tokens") or 0)
                current_output = int(usage.get("output_tokens") or 0)
                input_tokens += current_input
                output_tokens += current_output
                if current_input or current_output:
                    model_calls += 1
            estimated_cost += float(row.get("estimated_cost") or 0)
        return EngineUsage(
            model_call_count=model_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimated_cost,
        )

    def _artifact_dir(self, engine_run_id: str) -> Path:
        path = (self.settings.artifacts_root / engine_run_id).resolve()
        if self.settings.artifacts_root.resolve() not in path.parents:
            raise ValueError("artifact path escaped configured root")
        return path


def _progress(stage: str) -> int:
    return _STAGE_PROGRESS.get(stage, 10)


def _media_type(fmt: str) -> str:
    return {
        "json": "application/json",
        "markdown": "text/markdown; charset=utf-8",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "trace": "application/x-ndjson",
    }.get(fmt, "application/octet-stream")


def _artifact(artifact_id: str, path: Path, fmt: str) -> EngineArtifact:
    return EngineArtifact(
        artifact_id=artifact_id,
        format=fmt,
        display_name=path.name,
        media_type=_media_type(fmt),
        size_bytes=path.stat().st_size,
        sha256=sha256_file(path),
    )
