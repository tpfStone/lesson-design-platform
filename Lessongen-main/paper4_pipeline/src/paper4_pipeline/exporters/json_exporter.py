"""Canonical UTF-8 JSON export for the selected best lesson plan."""

from __future__ import annotations

import json
from pathlib import Path

from paper4_pipeline.domain.models import LessonPlanVersion, PipelineResult, TaskMode
from paper4_pipeline.control.optimization import optimization_summary
from paper4_pipeline.exporters.common import atomic_write_text


def best_version(result: PipelineResult) -> LessonPlanVersion:
    return next(
        version for version in result.versions if version.version_id == result.best_version_id
    )


def export_best_json(result: PipelineResult, path: Path) -> Path:
    version = best_version(result)
    payload = {
        "schema_version": "paper4-lesson-plan-export-v0.1",
        "pipeline_version": "0.1.0",
        "run_id": result.run_id,
        "task_id": result.task_id,
        "run_status": result.status.value,
        "stop_reason": result.stop_reason.value if result.stop_reason else None,
        "recovery_only": result.status.value == "failed",
        "requires_human_review": result.status.value == "needs_human",
        "best_version_id": result.best_version_id,
        "last_version_id": result.last_version_id,
        "document_hash": version.document_hash,
        "design_blueprint": (
            result.design_blueprint.model_dump(mode="json")
            if result.design_blueprint
            else None
        ),
        "lesson_plan": version.document.model_dump(mode="json"),
    }
    if result.task_mode == TaskMode.OPTIMIZE:
        payload["optimization"] = optimization_summary(result)
    atomic_write_text(
        path,
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
    )
    return path


def export_run_result_json(result: PipelineResult, path: Path) -> Path:
    atomic_write_text(
        path,
        json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
    )
    return path
