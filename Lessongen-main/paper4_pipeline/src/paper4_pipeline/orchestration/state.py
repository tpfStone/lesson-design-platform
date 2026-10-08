"""JSON-safe checkpoint state for LangGraph orchestration."""

from __future__ import annotations

import json
from typing import TypedDict

from pydantic import JsonValue


class PipelineState(TypedDict, total=False):
    schema_version: str
    run_id: str
    task: dict[str, JsonValue]
    config: dict[str, JsonValue]
    started_at: str
    workspace_dir: str
    trace_path: str
    design_blueprint: dict[str, JsonValue] | None
    versions: list[dict[str, JsonValue]]
    current_version_id: str
    critique_history: list[dict[str, JsonValue]]
    current_critique_batch: dict[str, JsonValue] | None
    validation_batches: list[dict[str, JsonValue]]
    rewrite_records: list[dict[str, JsonValue]]
    route_decisions: list[dict[str, JsonValue]]
    version_selections: list[dict[str, JsonValue]]
    iterations: list[dict[str, JsonValue]]
    optimization_quality_gate: dict[str, JsonValue] | None
    optimization_comparison: dict[str, JsonValue] | None
    knowledge_bundles: list[dict[str, JsonValue]]
    model_call_count: int
    token_usage: dict[str, JsonValue]
    estimated_cost: float
    score_deltas: list[float]
    cycle_start: dict[str, JsonValue] | None
    pending_iteration: dict[str, JsonValue] | None
    stop_reason: str | None
    status: str
    errors: list[str]


def assert_json_safe_state(state: PipelineState) -> None:
    """Fail early if a model client, Path, or other runtime object leaks in."""

    json.dumps(state, ensure_ascii=False, allow_nan=False, sort_keys=True)
