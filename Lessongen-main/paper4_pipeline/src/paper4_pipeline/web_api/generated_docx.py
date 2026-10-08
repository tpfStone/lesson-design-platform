"""Recover the canonical document behind an unmodified Word export.

The exported JSON is the lossless source of the Word presentation. Re-parsing our
own Word with an LLM is both less faithful and needlessly expensive. A checksum
match against the export manifest is required before this shortcut is allowed.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from paper4_pipeline.domain.models import LessonPlanDocument
from paper4_pipeline.exporters.common import sha256_file
from paper4_pipeline.web_api.schemas import (
    EngineLessonInput,
    NormalizedLessonInput,
    RawLessonDocument,
)


def _identity_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"[\s《》〈〉“”‘’]", "", normalized).casefold()


def _equivalent_subject(left: str, right: str) -> bool:
    def core(value: str) -> str:
        normalized = _identity_text(value)
        for prefix in ("小学", "初中", "高中", "职高"):
            if normalized.startswith(prefix):
                return normalized[len(prefix):]
        return normalized
    return bool(core(left)) and core(left) == core(right)


def restore_generated_docx(
    raw: RawLessonDocument,
    task_input: EngineLessonInput,
    *,
    task_id: str,
    plan_id: str,
    artifacts_root: Path,
) -> NormalizedLessonInput | None:
    """Return a trusted original structure, or None for an external/edited Word."""

    if not artifacts_root.is_dir():
        return None

    for manifest_path in artifacts_root.glob("*/manifest.json"):
        folder = manifest_path.parent
        docx_path = folder / "best_lesson_plan.docx"
        json_path = folder / "best_lesson_plan.json"
        if not docx_path.is_file() or not json_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifacts = {
                item["artifact_id"]: item
                for item in manifest["artifacts"]
                if isinstance(item, dict) and isinstance(item.get("artifact_id"), str)
            }
            word_record = artifacts["best-plan-docx"]
            json_record = artifacts["best-plan-json"]
            if (
                word_record.get("status") != "ok"
                or json_record.get("status") != "ok"
                or word_record.get("sha256") != raw.source_sha256
            ):
                continue
            # Do not trust absolute paths from a manifest; resolve only fixed
            # filenames inside its directory and verify both file contents.
            if (
                sha256_file(docx_path) != raw.source_sha256
                or sha256_file(json_path) != json_record.get("sha256")
            ):
                continue
            export = json.loads(json_path.read_text(encoding="utf-8"))
            if (
                export.get("schema_version") != "paper4-lesson-plan-export-v0.1"
                or export.get("recovery_only") is not False
                or export.get("run_id") != manifest.get("run_id")
            ):
                continue
            document = LessonPlanDocument.model_validate(export["lesson_plan"])
            metadata = document.metadata
            if (
                not _equivalent_subject(metadata.subject, task_input.subject)
                or _identity_text(metadata.grade) != _identity_text(task_input.grade)
                or _identity_text(metadata.topic) != _identity_text(task_input.topic)
                or metadata.duration_minutes != task_input.duration_minutes
            ):
                continue
            warnings = list(raw.warnings)
            provenance = {
                key: "user" for key in
                ("subject", "grade", "topic", "duration_minutes")
            }
            changes = {}
            for key in ("subject", "grade", "topic"):
                requested = getattr(task_input, key)
                original = getattr(metadata, key)
                if requested != original:
                    changes[key] = requested
                    warnings.append(
                        f"原稿{key}为“{original}”，本次输入为“{requested}”；"
                        "已确认等价并采用本次输入"
                    )
            if task_input.textbook_version:
                provenance["textbook_version"] = "user"
                if document.metadata.textbook_version != task_input.textbook_version:
                    warnings.append(
                        "用户指定的教材版本与原稿不同；已采用用户输入，"
                        "请核对教学内容是否仍适用"
                    )
                    changes["textbook_version"] = task_input.textbook_version
            else:
                provenance["textbook_version"] = "file"
            if changes:
                document = document.model_copy(update={
                    "metadata": metadata.model_copy(update=changes)
                })

            locators = [
                (item.locator, item.text)
                for item in raw.paragraphs
            ] + [
                (cell.locator, cell.text)
                for table in raw.tables for cell in table.cells
            ]
            preservation_map: dict[str, list[str]] = {}
            for requirement in task_input.must_preserve_content:
                needle = requirement.strip().casefold()
                matches = [locator for locator, text in locators
                           if needle and needle in text.casefold()]
                preservation_map[requirement] = matches
                if not matches:
                    warnings.append(
                        f"保留要求“{requirement}”未能逐字定位到 Word 原文；"
                        "原稿已完整导入，但改写后需人工核对该要求"
                    )
            document = document.model_copy(update={"task_id": task_id, "plan_id": plan_id})
            return NormalizedLessonInput(
                source_sha256=raw.source_sha256,
                normalizer_prompt_version="verified-export-v1",
                metadata_provenance=provenance,
                lesson_plan=document,
                preserved_content_map=preservation_map,
                warnings=[*warnings, "已校验原生 Word 与结构化教案一致，跳过重复模型解析"],
                model_metadata={
                    "provider": "verified_export", "attempts": 0,
                    "source_run_id": manifest["run_id"],
                },
            )
        except (OSError, ValueError, KeyError, TypeError):
            # An incomplete or tampered artifact must never be accepted as a
            # trusted source. The model-backed importer remains available.
            continue
    return None
