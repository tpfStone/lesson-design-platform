"""Local append-only event trace with conservative secret redaction."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from paper4_pipeline.domain.models import TokenUsage


_SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "access_token",
    "refresh_token",
}


def redact(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in _SECRET_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "paper4-trace-event-v0.1"
    sequence: int = Field(ge=1)
    event_id: str
    run_id: str
    task_id: str
    event_type: str
    stage: str
    actor_profile_id: str = "program"
    profile_version: str = "0.1"
    knowledge_bundle_id: str = ""
    round_index: int = Field(default=0, ge=0)
    version_id: str = ""
    input_summary: JsonValue = None
    output_summary: JsonValue = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    estimated_cost: float = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0, ge=0)
    status: str = "ok"
    error: str = ""
    timestamp: datetime


class TraceStore:
    """One JSONL file per run; prior events are never rewritten."""

    def __init__(
        self,
        workspace: Path,
        run_id: str,
        task_id: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.task_id = task_id
        self.path = self.workspace / "trace.jsonl"
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sequence = self._existing_count()

    def _existing_count(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())

    def append(
        self,
        *,
        event_type: str,
        stage: str,
        actor_profile_id: str = "program",
        knowledge_bundle_id: str = "",
        round_index: int = 0,
        version_id: str = "",
        input_summary: JsonValue = None,
        output_summary: JsonValue = None,
        token_usage: TokenUsage | None = None,
        estimated_cost: float = 0.0,
        duration_seconds: float = 0.0,
        status: str = "ok",
        error: str = "",
    ) -> TraceEvent:
        self._sequence += 1
        event = TraceEvent(
            sequence=self._sequence,
            event_id=f"{self.run_id}-event-{self._sequence:04d}",
            run_id=self.run_id,
            task_id=self.task_id,
            event_type=event_type,
            stage=stage,
            actor_profile_id=actor_profile_id,
            knowledge_bundle_id=knowledge_bundle_id,
            round_index=round_index,
            version_id=version_id,
            input_summary=redact(input_summary),
            output_summary=redact(output_summary),
            token_usage=token_usage or TokenUsage(),
            estimated_cost=estimated_cost,
            duration_seconds=duration_seconds,
            status=status,
            error=error,
            timestamp=self._clock(),
        )
        payload = event.model_dump(mode="json")
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
            handle.flush()
        return event
