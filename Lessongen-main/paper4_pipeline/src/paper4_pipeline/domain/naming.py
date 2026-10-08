"""Readable, collision-resistant names for tasks and run directories."""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime

from paper4_pipeline.domain.models import LessonTask


_WINDOWS_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")
_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def safe_name_component(value: str, *, max_length: int = 24) -> str:
    """Keep Chinese readability while removing unsafe Windows filename text."""

    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = _WINDOWS_FORBIDDEN.sub("-", normalized)
    normalized = _WHITESPACE.sub("-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip(" .-")
    if not normalized:
        normalized = "lesson"
    if normalized.upper() in _RESERVED:
        normalized = f"lesson-{normalized}"
    return normalized[:max_length].rstrip(" .-") or "lesson"


def automatic_task_id(
    subject: str,
    grade: str,
    topic: str,
    *,
    now: datetime | None = None,
    suffix: str | None = None,
) -> str:
    moment = now or datetime.now().astimezone()
    stamp = moment.strftime("%Y%m%d-%H%M%S")
    readable = "-".join(
        safe_name_component(item, max_length=16)
        for item in (subject, grade, topic)
    )
    unique = safe_name_component(suffix or uuid.uuid4().hex[:6], max_length=8)
    return f"lesson-{stamp}-{readable}-{unique}"


def automatic_run_id(
    task: LessonTask,
    *,
    label: str = "",
    now: datetime | None = None,
    suffix: str | None = None,
) -> str:
    """Create a readable run folder; an optional label never removes uniqueness."""

    moment = now or datetime.now().astimezone()
    stamp = moment.strftime("%Y%m%d-%H%M%S")
    if label.strip():
        readable = safe_name_component(label, max_length=36)
    else:
        readable = "-".join(
            safe_name_component(item, max_length=16)
            for item in (task.subject, task.grade, task.topic)
        )
    unique = safe_name_component(suffix or uuid.uuid4().hex[:6], max_length=8)
    return f"{stamp}-{readable}-{unique}"
