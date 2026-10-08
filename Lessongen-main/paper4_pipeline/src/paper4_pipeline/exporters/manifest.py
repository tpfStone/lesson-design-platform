"""Artifact orchestration; Word remains an optional, isolated exporter."""

from __future__ import annotations

import json
from pathlib import Path

from paper4_pipeline.domain.models import (
    ArtifactManifest,
    ArtifactRecord,
    PipelineResult,
    RunStatus,
    TaskMode,
)
from paper4_pipeline.exporters.common import atomic_write_text, sha256_file
from paper4_pipeline.exporters.json_exporter import (
    best_version,
    export_best_json,
    export_run_result_json,
)
from paper4_pipeline.exporters.optimization_report import export_optimization_report
from paper4_pipeline.control.optimization import unselected_revised_candidate


def export_artifacts(
    result: PipelineResult,
    output_dir: Path,
    *,
    include_docx: bool = False,
) -> PipelineResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    if not result.versions:
        export_run_result_json(result, output_dir / "run_result.json")
        return result
    # A degraded run yields explicitly named recovery files. Their own payload
    # and heading carry the FAILED status; no success manifest or Word file is
    # produced.
    degraded = result.status == RunStatus.FAILED
    records: list[ArtifactRecord] = []
    stem = "recovery_lesson_plan" if degraded else "best_lesson_plan"
    json_path = export_best_json(result, output_dir / f"{stem}.json")
    records.append(
        ArtifactRecord(
            artifact_id=("recovery" if degraded else "best") + "-plan-json",
            format="json",
            path=str(json_path.resolve()),
            sha256=sha256_file(json_path),
        )
    )
    if degraded:
        if result.task_mode == TaskMode.OPTIMIZE:
            export_optimization_report(result, output_dir)
        export_run_result_json(result, output_dir / "run_result.json")
        return result
    if include_docx:
        docx_path = output_dir / "best_lesson_plan.docx"
        try:
            from paper4_pipeline.exporters.docx_exporter import export_best_docx

            export_best_docx(result, docx_path)
            records.append(
                ArtifactRecord(
                    artifact_id="best-plan-docx",
                    format="docx",
                    path=str(docx_path.resolve()),
                    sha256=sha256_file(docx_path),
                )
            )
        except Exception as exc:
            records.append(
                ArtifactRecord(
                    artifact_id="best-plan-docx",
                    format="docx",
                    path=str(docx_path.resolve()),
                    sha256="0" * 64,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    if result.task_mode == TaskMode.OPTIMIZE and include_docx:
        candidate = unselected_revised_candidate(result)
        if candidate is not None:
            candidate_path = output_dir / "revised_candidate.docx"
            try:
                from paper4_pipeline.exporters.docx_exporter import export_docx

                export_docx(
                    candidate.document, candidate_path, run_id=result.run_id,
                    best_version_id=candidate.version_id,
                    last_version_id=result.last_version_id,
                )
                records.append(ArtifactRecord(
                    artifact_id="revised-candidate-docx", format="docx",
                    path=str(candidate_path.resolve()), sha256=sha256_file(candidate_path),
                ))
            except Exception as exc:
                records.append(ArtifactRecord(
                    artifact_id="revised-candidate-docx", format="docx",
                    path=str(candidate_path.resolve()), sha256="0" * 64,
                    status="error", error=f"{type(exc).__name__}: {exc}",
                ))
    if result.task_mode == TaskMode.OPTIMIZE:
        report_json = export_optimization_report(result, output_dir)
        records.append(ArtifactRecord(
            artifact_id="optimization-report-json",
            format="json",
            path=str(report_json.resolve()),
            sha256=sha256_file(report_json),
        ))
    trace_path = Path(result.trace_path)
    if trace_path.is_file():
        records.append(
            ArtifactRecord(
                artifact_id="run-trace",
                format="trace",
                path=str(trace_path.resolve()),
                sha256=sha256_file(trace_path),
            )
        )
    selected = best_version(result)
    manifest = ArtifactManifest(
        manifest_id=f"manifest-{result.run_id}",
        run_id=result.run_id,
        best_version_id=result.best_version_id,
        last_version_id=result.last_version_id,
        lesson_plan_schema_version=selected.document.schema_version,
        template_id=selected.document.template_id,
        template_version="compact-reference-guide-v0.1",
        artifacts=records,
    )
    updated = PipelineResult.model_validate(
        {**result.model_dump(mode="python"), "artifacts": manifest}
    )
    export_run_result_json(updated, output_dir / "run_result.json")
    atomic_write_text(
        output_dir / "manifest.json",
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
    )
    return updated
