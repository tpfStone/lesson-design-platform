"""Teacher-readable and machine-readable evidence for optimization runs."""

from __future__ import annotations

import json
from pathlib import Path

from paper4_pipeline.control.optimization import optimization_summary
from paper4_pipeline.domain.models import PipelineResult
from paper4_pipeline.exporters.common import atomic_write_text


def export_optimization_report(result: PipelineResult, output_dir: Path) -> Path:
    summary = optimization_summary(result)
    baseline = min(result.versions, key=lambda item: (item.iteration, item.version_id))
    selected = next(item for item in result.versions
                    if item.version_id == result.best_version_id)
    payload = {
        "schema_version": "paper4-optimization-report-v1",
        "run_id": result.run_id,
        "status": result.status.value,
        "summary": summary,
        "baseline_plan": baseline.document.model_dump(mode="json"),
        "selected_plan": selected.document.model_dump(mode="json"),
        "critiques": [item.model_dump(mode="json") for item in result.critiques],
        "validation_batches": [item.model_dump(mode="json") for item in result.validation_batches],
        "rewrite_records": [item.model_dump(mode="json") for item in result.rewrite_records],
        "route_decisions": [item.model_dump(mode="json") for item in result.route_decisions],
        "iterations": [item.model_dump(mode="json") for item in result.iterations],
    }
    json_path = output_dir / "optimization_report.json"
    atomic_write_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    return json_path
