"""Application service for real DeepSeek Paper#4 runs."""

from __future__ import annotations

from pathlib import Path

from paper4_pipeline.agents.live import build_live_suite
from paper4_pipeline.domain.models import ExperimentConfig, LessonTask, PipelineResult
from paper4_pipeline.exporters.manifest import export_artifacts
from paper4_pipeline.orchestration.graph import Paper4Workflow


class PipelineService:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root.resolve()

    def run(
        self,
        task: LessonTask,
        config: ExperimentConfig,
        *,
        run_id: str | None = None,
        include_docx: bool | None = None,
    ) -> PipelineResult:
        agents = build_live_suite(config)
        workflow = Paper4Workflow(agents, self.output_root)
        result = workflow.run(task, config, run_id=run_id)
        artifact_dir = Path(result.trace_path).parent
        return export_artifacts(
            result,
            artifact_dir,
            include_docx=config.enable_docx
            if include_docx is None
            else include_docx,
        )
