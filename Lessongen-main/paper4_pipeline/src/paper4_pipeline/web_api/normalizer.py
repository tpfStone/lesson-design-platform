"""Model-backed, auditable conversion from extracted DOCX to LessonPlanDocument."""

from __future__ import annotations

from dataclasses import asdict

from paper4_pipeline.agents.prompts import load_prompt
from paper4_pipeline.domain.models import ExperimentConfig
from paper4_pipeline.providers.openai_compatible import OpenAICompatibleProvider
from paper4_pipeline.web_api.schemas import (
    EngineLessonInput,
    NormalizationModelOutput,
    NormalizedLessonInput,
    RawLessonDocument,
)
from paper4_pipeline.web_api.segmented_normalizer import SegmentedDocxNormalizer


class DocxNormalizer:
    def __init__(self, config: ExperimentConfig) -> None:
        base = config.role_model_configs[config.writer_profile_id]
        settings = base.model_copy(
            update={"temperature": 0.1, "max_tokens": min(base.max_tokens, 8192)}
        )
        self.provider = OpenAICompatibleProvider(settings)
        self.prompt = load_prompt("docx_normalizer_prompt")

    def normalize(
        self,
        raw: RawLessonDocument,
        task_input: EngineLessonInput,
        *,
        task_id: str,
        plan_id: str,
    ) -> NormalizedLessonInput:
        # External classroom plans of moderate length can exceed the provider's
        # one-response output limit even though the DOCX file itself is small.
        # Split *output responsibilities* before the first paid call.
        if raw.character_count() > 4500:
            return SegmentedDocxNormalizer(self.provider).normalize(
                raw, task_input, task_id=task_id, plan_id=plan_id,
            )
        authoritative = {
            "subject": task_input.subject,
            "grade": task_input.grade,
            "topic": task_input.topic,
            "duration_minutes": task_input.duration_minutes,
        }
        # An empty optional textbook field is not an instruction to erase a
        # textbook version explicitly present in the uploaded lesson plan.
        if task_input.textbook_version:
            authoritative["textbook_version"] = task_input.textbook_version

        def validate(value: NormalizationModelOutput) -> None:
            plan = value.lesson_plan
            if plan.task_id != task_id or plan.plan_id != plan_id:
                raise ValueError("normalizer changed required task or plan identity")
            actual = plan.metadata.model_dump(mode="python")
            for key, expected in authoritative.items():
                if actual[key] != expected:
                    raise ValueError(f"normalizer changed authoritative metadata: {key}")
            for key in authoritative:
                if value.metadata_provenance.get(key) != "user":
                    raise ValueError(f"metadata provenance must mark {key} as user")
            missing_preserved = set(task_input.must_preserve_content) - set(
                value.preserved_content_map
            )
            if missing_preserved:
                raise ValueError(
                    "normalizer did not account for must-preserve items: "
                    + ", ".join(sorted(missing_preserved))
                )

        response = self.provider.invoke_structured(
            prompt=self.prompt,
            input_payload={
                "required_identity": {
                    "schema_version": "paper4-lesson-plan-v0.1",
                    "task_id": task_id,
                    "plan_id": plan_id,
                    "template_id": "general_v0_1",
                },
                "authoritative_metadata": authoritative,
                "optimization_focus": task_input.optimization_focus,
                "must_preserve_content": task_input.must_preserve_content,
                "raw_document": raw.model_dump(mode="json"),
            },
            output_schema=NormalizationModelOutput,
            stage="docx_normalizer",
            result_validator=validate,
        )
        return NormalizedLessonInput(
            source_sha256=raw.source_sha256,
            normalizer_prompt_version=self.prompt.version,
            metadata_provenance=response.value.metadata_provenance,
            lesson_plan=response.value.lesson_plan,
            preserved_content_map=response.value.preserved_content_map,
            raw_locator_coverage=response.value.raw_locator_coverage,
            warnings=[*raw.warnings, *response.value.warnings],
            usage=response.usage,
            estimated_cost=response.estimated_cost,
            model_metadata=asdict(response.metadata),
        )
