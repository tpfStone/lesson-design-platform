"""Bounded, source-grounded import of external lesson-plan Word documents.

The Word reader supplies ordered blocks. The model interprets pedagogical
meaning in two small output contracts; it is never asked to echo the entire
source document and locator maps in one response.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from paper4_pipeline.agents.prompts import load_prompt
from paper4_pipeline.domain.models import (
    LearningObjective, LessonMetadata, LessonPlanDocument, ProcedureStep,
    StrictModel, TeachingArtifact, TeachingResource, TokenUsage,
)
from paper4_pipeline.providers.openai_compatible import (
    OpenAICompatibleProvider, ProviderInvocationError,
)
from paper4_pipeline.web_api.schemas import (
    EngineLessonInput, NormalizedLessonInput, RawBlock, RawLessonDocument,
)


class OverviewOutput(StrictModel):
    textbook_version: str = ""
    design_thesis: str = ""
    driving_question: str = ""
    learning_trajectory: list[str] = Field(default_factory=list)
    curriculum_standards: list[str] = Field(default_factory=list)
    content_analysis: str = ""
    student_analysis: str = ""
    learning_objectives: list[LearningObjective] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    difficult_points: list[str] = Field(default_factory=list)
    teaching_strategy: str = ""
    resources: list[TeachingResource] = Field(default_factory=list)
    assessment_plan: str = ""
    differentiation: str = ""
    homework: str = ""
    board_design: str = ""
    reflection: str = ""
    references: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_references(self) -> "OverviewOutput":
        for label, values in (
            ("objective_id", [x.objective_id for x in self.learning_objectives]),
            ("resource_id", [x.resource_id for x in self.resources]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} in Word overview")
        return self


class ActivityOutput(StrictModel):
    procedure_steps: list[ProcedureStep] = Field(default_factory=list)
    teaching_artifacts: list[TeachingArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


_OVERVIEW_TEXT_FIELDS = (
    "design_thesis", "driving_question", "content_analysis", "student_analysis",
    "teaching_strategy", "assessment_plan", "differentiation", "homework",
    "board_design", "reflection",
)
_OVERVIEW_LIST_FIELDS = (
    "learning_trajectory", "curriculum_standards", "key_points",
    "difficult_points", "references",
)


def _merge_overviews(parts: list[OverviewOutput]) -> OverviewOutput:
    if len(parts) == 1:
        return parts[0]
    merged: dict[str, object] = {}
    warnings: list[str] = []
    versions = [item.textbook_version for item in parts if item.textbook_version]
    merged["textbook_version"] = versions[0] if versions else ""
    if len(set(versions)) > 1:
        warnings.append("原稿不同片段出现多个教材版本，请教师核对")
    for field in _OVERVIEW_TEXT_FIELDS:
        values = list(dict.fromkeys(getattr(item, field).strip() for item in parts
                                    if getattr(item, field).strip()))
        merged[field] = "\n\n".join(values)
    for field in _OVERVIEW_LIST_FIELDS:
        merged[field] = list(dict.fromkeys(
            value for item in parts for value in getattr(item, field)
        ))
    objectives: list[LearningObjective] = []
    resources: list[TeachingResource] = []
    for part in parts:
        warnings.extend(part.warnings)
        for item in part.learning_objectives:
            objectives.append(item.model_copy(update={
                "objective_id": f"import-objective-{len(objectives) + 1:03d}"
            }))
        for item in part.resources:
            resources.append(item.model_copy(update={
                "resource_id": f"import-resource-{len(resources) + 1:03d}"
            }))
    merged["learning_objectives"] = objectives
    merged["resources"] = resources
    merged["warnings"] = warnings
    return OverviewOutput.model_validate(merged)


def _ordered_blocks(raw: RawLessonDocument) -> list[RawBlock]:
    if raw.ordered_blocks:
        return raw.ordered_blocks
    # Old saved raw documents predate ordered extraction. Their original body
    # order is unknowable; preserve all text and explicitly warn at the caller.
    return [
        RawBlock(locator=p.locator, kind="paragraph", text=p.text, style=p.style)
        for p in raw.paragraphs
    ] + [
        RawBlock(locator=f"{t.locator}/row:{row + 1}", kind="table_row",
                 text=" | ".join(f"列{c.column + 1}: {c.text}" for c in t.cells if c.row == row))
        for t in raw.tables for row in range(t.rows)
        if any(c.row == row for c in t.cells)
    ]


def _chunks(blocks: list[RawBlock], max_characters: int = 2600) -> list[list[dict[str, str]]]:
    chunks: list[list[dict[str, str]]] = []
    current: list[dict[str, str]] = []
    size = 0
    for block in blocks:
        # A single huge table cell can exceed the budget; split its *text*
        # without dropping any characters or pretending it is a new source.
        text = block.text
        parts = [text[i:i + max_characters] for i in range(0, len(text), max_characters)]
        for index, part in enumerate(parts):
            entry = {
                "locator": block.locator + (f"/part:{index + 1}" if len(parts) > 1 else ""),
                "kind": block.kind, "style": block.style, "text": part,
            }
            if current and size + len(part) > max_characters:
                chunks.append(current)
                current, size = [], 0
            current.append(entry)
            size += len(part)
    if current:
        chunks.append(current)
    return chunks


def _preservation_map(raw: RawLessonDocument, requirements: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    items = [(p.locator, p.text) for p in raw.paragraphs] + [
        (c.locator, c.text) for table in raw.tables for c in table.cells
    ]
    mapping: dict[str, list[str]] = {}
    warnings: list[str] = []
    for requirement in requirements:
        needle = requirement.strip().casefold()
        mapping[requirement] = [locator for locator, text in items
                                if needle and needle in text.casefold()]
        if not mapping[requirement]:
            warnings.append(f"保留要求“{requirement}”未逐字定位；改写后必须人工核对")
    return mapping, warnings


class SegmentedDocxNormalizer:
    def __init__(self, provider: OpenAICompatibleProvider) -> None:
        self.provider = provider
        self.overview_prompt = load_prompt("docx_overview_prompt")
        self.activities_prompt = load_prompt("docx_activities_prompt")

    def normalize(
        self, raw: RawLessonDocument, task_input: EngineLessonInput,
        *, task_id: str, plan_id: str,
    ) -> NormalizedLessonInput:
        blocks = _ordered_blocks(raw)
        if not blocks:
            raise ValueError("Word 中没有可结构化的正文或表格")
        batches = _chunks(blocks)
        if len(batches) > 12:
            raise ValueError(
                "外部 Word 的可读教学内容超出当前分段导入预算；"
                "请按课时拆分文档后再分别优化"
            )
        usage = TokenUsage()
        cost = 0.0
        attempts = 0

        def call(*, prompt, payload, schema, stage):
            nonlocal usage, cost, attempts
            try:
                result = self.provider.invoke_structured(
                    prompt=prompt, input_payload=payload,
                    output_schema=schema, stage=stage,
                )
            except ProviderInvocationError as exc:
                usage = TokenUsage(
                    input_tokens=usage.input_tokens + exc.usage.input_tokens,
                    output_tokens=usage.output_tokens + exc.usage.output_tokens,
                )
                cost += exc.estimated_cost
                attempts += exc.attempts
                raise ProviderInvocationError(
                    str(exc), attempts=attempts,
                    usage=usage, estimated_cost=cost,
                ) from exc
            usage = TokenUsage(
                input_tokens=usage.input_tokens + result.usage.input_tokens,
                output_tokens=usage.output_tokens + result.usage.output_tokens,
            )
            cost += result.estimated_cost
            attempts += result.metadata.attempts
            return result.value

        # Overview calls also have bounded input. Long files use several
        # contiguous groups rather than sending 120,000 characters at once.
        overview_groups = (
            [[entry for batch in batches for entry in batch]]
            if raw.character_count() <= 12000 else
            [[entry for batch in batches[i:i + 4] for entry in batch]
             for i in range(0, len(batches), 4)]
        )
        overview_parts: list[OverviewOutput] = []
        def read_overview(group: list[dict[str, str]], index: int) -> None:
            try:
                overview_parts.append(call(
                    prompt=self.overview_prompt,
                    payload={"subject": task_input.subject, "grade": task_input.grade,
                             "topic": task_input.topic,
                             "duration_minutes": task_input.duration_minutes,
                             "batch_index": index, "batch_count": len(overview_groups),
                             "source_blocks": group},
                    schema=OverviewOutput, stage="docx_overview",
                ))
            except ProviderInvocationError as exc:
                if "length limit was reached" not in str(exc).lower() or len(group) < 2:
                    raise
                midpoint = len(group) // 2
                read_overview(group[:midpoint], index)
                read_overview(group[midpoint:], index)

        for index, group in enumerate(overview_groups, start=1):
            read_overview(group, index)
        overview = _merge_overviews(overview_parts)
        warnings = [*raw.warnings, *overview.warnings]
        if not raw.ordered_blocks:
            warnings.append("旧版提取记录未保存段落与表格的交错顺序")
        artifacts: list[TeachingArtifact] = []
        steps: list[ProcedureStep] = []
        artifact_ids: dict[str, str] = {}
        known_objectives = {item.objective_id for item in overview.learning_objectives}
        known_resources = {item.resource_id for item in overview.resources}
        table_headers = {
            item.locator.split("/row:", 1)[0]: item.text
            for item in blocks
            if item.kind == "table_row" and item.locator.endswith("/row:1")
            and any(word in item.text for word in ("环节", "时间", "教师", "学生", "活动"))
        }
        preceding_headings: dict[str, str] = {}
        current_heading = ""
        for item in blocks:
            if item.kind == "paragraph" and (
                "heading" in item.style.casefold()
                or (len(item.text) <= 24 and item.text.rstrip().endswith(("：", ":")))
            ):
                current_heading = item.text
            preceding_headings[item.locator] = current_heading
        for index, batch in enumerate(batches, start=1):
            batch_tables = {
                entry["locator"].split("/row:", 1)[0]
                for entry in batch if entry["kind"] == "table_row"
            }
            activity: ActivityOutput = call(
                prompt=self.activities_prompt,
                payload={
                    "batch_index": index, "batch_count": len(batches),
                    "subject": task_input.subject, "grade": task_input.grade,
                    "topic": task_input.topic, "duration_minutes": task_input.duration_minutes,
                    "known_objective_ids": sorted(known_objectives),
                    "known_resource_ids": sorted(known_resources),
                    "preceding_heading_context": preceding_headings.get(
                        batch[0]["locator"].split("/part:", 1)[0], ""
                    ),
                    "table_header_context": {
                        name: table_headers[name] for name in batch_tables
                        if name in table_headers
                    },
                    "source_blocks": batch,
                },
                schema=ActivityOutput, stage="docx_activities",
            )
            warnings.extend(activity.warnings)
            for item in activity.teaching_artifacts:
                new_id = f"import-artifact-{len(artifacts) + 1:03d}"
                if item.artifact_id in artifact_ids:
                    warnings.append(f"重复材料 ID {item.artifact_id}，已按原文顺序重编号")
                artifact_ids[item.artifact_id] = new_id
                artifacts.append(item.model_copy(update={"artifact_id": new_id}))
            for item in activity.procedure_steps:
                unknown_objectives = set(item.objective_ids) - known_objectives
                unknown_resources = set(item.resource_ids) - known_resources
                if unknown_objectives or unknown_resources:
                    warnings.append(
                        f"步骤 {item.stage} 引用了未识别的目标/资源 ID，已移除无效引用"
                    )
                missing_artifacts = set(item.artifact_ids) - set(artifact_ids)
                if missing_artifacts:
                    warnings.append(f"步骤 {item.stage} 引用的材料尚未识别：{sorted(missing_artifacts)}")
                steps.append(item.model_copy(update={
                    "step_id": f"import-step-{len(steps) + 1:03d}",
                    "objective_ids": [x for x in item.objective_ids if x in known_objectives],
                    "resource_ids": [x for x in item.resource_ids if x in known_resources],
                    "artifact_ids": [artifact_ids[x] for x in item.artifact_ids if x in artifact_ids],
                }))
        if not steps:
            raise ValueError("Word 已读取，但未识别到可执行的教学步骤；请核对文档是否为教案")
        # Duration is a task constraint. Preserve proportions, record the edit,
        # and never silently claim the source supplied the adjusted timings.
        total_minutes = sum(step.duration_minutes for step in steps)
        if total_minutes != task_input.duration_minutes:
            if len(steps) > task_input.duration_minutes:
                raise ValueError(
                    "识别出的教学步骤数超过课时分钟数，无法无损分配时间；请人工整理原稿"
                )
            remaining = task_input.duration_minutes
            adjusted: list[ProcedureStep] = []
            for index, step in enumerate(steps):
                slots_left = len(steps) - index - 1
                minutes = (remaining if not slots_left else max(
                    1, min(remaining - slots_left,
                           round(step.duration_minutes * task_input.duration_minutes / total_minutes))
                ))
                adjusted.append(step.model_copy(update={"duration_minutes": minutes}))
                remaining -= minutes
            steps = adjusted
            warnings.append(
                f"原稿各环节时间合计 {total_minutes} 分钟；为符合本次课时 "
                f"{task_input.duration_minutes} 分钟，已按比例调整，请教师核对"
            )
        preservation_map, preserve_warnings = _preservation_map(
            raw, task_input.must_preserve_content,
        )
        warnings.extend(preserve_warnings)
        textbook = task_input.textbook_version or overview.textbook_version
        overview_data = overview.model_dump(exclude={"textbook_version", "warnings"})
        document = LessonPlanDocument(
            plan_id=plan_id, task_id=task_id,
            metadata=LessonMetadata(
                subject=task_input.subject, grade=task_input.grade,
                topic=task_input.topic, duration_minutes=task_input.duration_minutes,
                textbook_version=textbook,
            ),
            **overview_data,
            procedure_steps=steps, teaching_artifacts=artifacts,
        )
        return NormalizedLessonInput(
            source_sha256=raw.source_sha256,
            normalizer_prompt_version="segmented-v1",
            metadata_provenance={
                "subject": "user", "grade": "user", "topic": "user",
                "duration_minutes": "user",
                "textbook_version": "user" if task_input.textbook_version else
                ("file" if overview.textbook_version else "inferred"),
            },
            lesson_plan=document, preserved_content_map=preservation_map,
            warnings=warnings, usage=usage, estimated_cost=cost,
            model_metadata={"provider": self.provider.settings.provider,
                            "model": self.provider.settings.model_name,
                            "attempts": attempts, "source_batches": len(batches),
                            "overview_prompt_sha256": self.overview_prompt.sha256,
                            "activities_prompt_sha256": self.activities_prompt.sha256},
        )
