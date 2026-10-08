"""A bounded second rewrite route: model proposes edits, code applies them.

The full-document rewriter is useful for coherent redesign, but asking it to
re-emit a large lesson plan for five local issues is costly and brittle. This
route sends relevant source slices and receives only modified JSON values.
"""

from __future__ import annotations

import copy
import json
from collections import defaultdict
from dataclasses import replace

from pydantic import Field, JsonValue, model_validator

from paper4_pipeline.agents.prompts import load_prompt
from paper4_pipeline.agents.protocols import AgentCallMetadata, AgentOutput
from paper4_pipeline.control.rules import hard_rule_regressions
from paper4_pipeline.domain.models import (
    CritiqueItem, LessonPlanDocument, LessonPlanVersion, LessonTask,
    RewriteChange, RewriteOutcome, StrictModel, TokenUsage,
)
from paper4_pipeline.providers.openai_compatible import (
    OpenAICompatibleProvider, ProviderInvocationError,
)


_EDITABLE_ROOTS = {
    "design_thesis", "driving_question", "learning_trajectory",
    "curriculum_standards", "content_analysis", "student_analysis",
    "learning_objectives", "key_points", "difficult_points",
    "teaching_strategy", "resources", "teaching_artifacts",
    "procedure_steps", "assessment_plan", "differentiation", "homework",
    "board_design", "reflection", "references", "template_extensions",
}


class ProposedEdit(StrictModel):
    critique_id: str = Field(min_length=1)
    path: str = Field(pattern=r"^/[^/]+(?:/[^/]+)*$")
    value: JsonValue
    reason: str = Field(min_length=1)


class PatchProposal(StrictModel):
    edits: list[ProposedEdit] = Field(default_factory=list, max_length=20)
    unresolved_critique_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_edits(self) -> "PatchProposal":
        paths = [item.path for item in self.edits]
        if len(paths) != len(set(paths)):
            raise ValueError("patch route cannot write the same path twice")
        if len(self.unresolved_critique_ids) != len(set(self.unresolved_critique_ids)):
            raise ValueError("duplicate unresolved critique ID")
        return self


def _segments(path: str) -> list[str]:
    if not path.startswith("/"):
        raise ValueError("edit path must be a JSON Pointer")
    return [part.replace("~1", "/").replace("~0", "~")
            for part in path.split("/")[1:]]


def _index(items: list[object], segment: str) -> int:
    if segment.isdigit():
        index = int(segment)
        if index < len(items):
            return index
        raise ValueError(f"edit path index out of range: {segment}")
    for index, item in enumerate(items):
        if isinstance(item, dict) and any(
            key.endswith("_id") and value == segment for key, value in item.items()
        ):
            return index
    raise ValueError(f"edit path ID not found: {segment}")


def _get(root: object, path: str) -> object:
    current = root
    for segment in _segments(path):
        if isinstance(current, dict):
            if segment not in current:
                raise ValueError(f"edit path does not exist: {path}")
            current = current[segment]
        elif isinstance(current, list):
            current = current[_index(current, segment)]
        else:
            raise ValueError(f"edit path does not exist: {path}")
    return current


def _replace(root: dict[str, object], path: str, value: JsonValue) -> object:
    parts = _segments(path)
    if not parts or parts[0] not in _EDITABLE_ROOTS:
        raise ValueError(f"forbidden rewrite path: {path}")
    parent: object = root
    for segment in parts[:-1]:
        if isinstance(parent, dict):
            if segment not in parent:
                raise ValueError(f"edit path does not exist: {path}")
            parent = parent[segment]
        elif isinstance(parent, list):
            parent = parent[_index(parent, segment)]
        else:
            raise ValueError(f"edit path does not exist: {path}")
    last = parts[-1]
    if isinstance(parent, dict):
        if last not in parent:
            raise ValueError(f"edit path does not exist: {path}")
        before = parent[last]
        parent[last] = value
    elif isinstance(parent, list):
        index = _index(parent, last)
        before = parent[index]
        parent[index] = value
    else:
        raise ValueError(f"edit path does not exist: {path}")
    if before == value:
        raise ValueError(f"patch claimed unchanged value: {path}")
    return before


def _brief(value: object, limit: int = 260) -> str:
    rendered = json.dumps(value, ensure_ascii=False, default=str)
    return rendered if len(rendered) <= limit else rendered[:limit] + "…"


def materialize_patch(
    proposal: PatchProposal, document: LessonPlanDocument,
    accepted: list[CritiqueItem], task: LessonTask, tolerance: int,
) -> RewriteOutcome:
    by_id = {item.critique_id: item for item in accepted}
    edits_by_id: dict[str, list[ProposedEdit]] = defaultdict(list)
    for edit in proposal.edits:
        if edit.critique_id not in by_id:
            raise ValueError(f"patch used non-accepted critique: {edit.critique_id}")
        edits_by_id[edit.critique_id].append(edit)
    unresolved = set(proposal.unresolved_critique_ids)
    if unresolved - set(by_id) or unresolved & set(edits_by_id):
        raise ValueError("patch unresolved IDs are unknown or also edited")
    if set(edits_by_id) | unresolved != set(by_id):
        raise ValueError("every accepted critique needs an edit or unresolved ID")
    source = document.model_dump(mode="json")
    candidate = copy.deepcopy(source)
    prior_values: dict[str, object] = {}
    for edit in proposal.edits:
        prior_values[edit.path] = _replace(candidate, edit.path, edit.value)
    revised = LessonPlanDocument.model_validate(candidate)
    if revised.metadata != document.metadata:
        raise ValueError("patch changed immutable metadata")
    regressions = hard_rule_regressions(document, revised, task, tolerance)
    if regressions:
        raise ValueError(
            "patch introduced a deterministic hard-rule regression: "
            + "; ".join(regressions)
        )
    changes = [RewriteChange(
        critique_id=critique_id,
        target_path=critique.target_path,
        edited_paths=[item.path for item in edits_by_id[critique_id]],
        lesson_location=critique.lesson_location,
        before_summary="；".join(
            f"{item.path}: {_brief(prior_values[item.path])}"
            for item in edits_by_id[critique_id]
        ),
        after_summary="；".join(
            f"{item.path}: {_brief(_get(candidate, item.path))}（{item.reason}）"
            for item in edits_by_id[critique_id]
        ),
        # A byte-level field change is not proof that an open-ended teaching
        # criticism was resolved. The deterministic verifier may certify the
        # small subset it can check; all others await independent review.
        implementation_status="partially_implemented",
    ) for critique_id, critique in by_id.items() if critique_id in edits_by_id]
    return RewriteOutcome(
        document=revised, changes=changes,
        unresolved_critique_ids=sorted(unresolved),
        unresolved_reasons={
            critique_id: "模型说明当前证据或约束下无法安全落实这条意见"
            for critique_id in unresolved
        },
    )


def _local_source(value: object, feedback: str) -> object:
    """Do not send an entire large list just because a critic used its root."""
    if not isinstance(value, list):
        return value
    matching = [
        item for item in value if isinstance(item, dict) and any(
            isinstance(identifier, str) and identifier in feedback
            for key, identifier in item.items() if key.endswith("_id")
        )
    ]
    if matching:
        return matching[:3]
    return [{
        "id": next((identifier for key, identifier in item.items()
                    if key.endswith("_id")), str(index)),
        "label": item.get("title") or item.get("name") or item.get("stage") or "",
        "duration_minutes": item.get("duration_minutes"),
    } for index, item in enumerate(value) if isinstance(item, dict)]


def _path_token(identifier: str) -> str:
    """Escape a model-visible ID as one JSON Pointer segment."""
    return identifier.replace("~", "~0").replace("/", "~1")


def _editable_path_bases(parent_path: str, content: object) -> list[str]:
    """Expose the document paths of local objects, never payload-only paths."""
    if not isinstance(content, list):
        return [parent_path]
    id_field = {
        "/procedure_steps": "step_id",
        "/resources": "resource_id",
        "/teaching_artifacts": "artifact_id",
        "/learning_objectives": "objective_id",
    }.get(parent_path)
    if id_field is None:
        return [parent_path]
    return [
        f"{parent_path}/{_path_token(identifier)}"
        for item in content
        if isinstance(item, dict)
        for identifier in [item.get(id_field) or item.get("id")]
        if isinstance(identifier, str)
    ]


def _referenced_objects(document: LessonPlanDocument, feedback: str) -> list[dict[str, object]]:
    """Keep resource, artifact and step namespaces distinct, even if IDs match."""
    result: list[dict[str, object]] = []
    for kind, root, identifier_name, items in (
        ("teaching_artifact", "/teaching_artifacts", "artifact_id", document.teaching_artifacts),
        ("resource", "/resources", "resource_id", document.resources),
        ("procedure_step", "/procedure_steps", "step_id", document.procedure_steps),
    ):
        for item in items:
            identifier = getattr(item, identifier_name)
            if identifier not in feedback:
                continue
            result.append({
                "kind": kind,
                "id": identifier,
                "editable_path_base": f"{root}/{_path_token(identifier)}",
                "content": item.model_dump(mode="json"),
            })
    return result


def patch_rewrite(
    provider: OpenAICompatibleProvider,
    task: LessonTask, version: LessonPlanVersion,
    accepted: list[CritiqueItem], round_index: int,
    duration_tolerance_minutes: int,
) -> AgentOutput[RewriteOutcome]:
    prompt = load_prompt("rewrite_patch_prompt")
    original = version.document.model_dump(mode="json")
    focus: list[dict[str, object]] = []
    feedback_text = "\n".join(
        f"{item.target_path}\n{item.lesson_location}\n"
        f"{item.issue}\n{item.evidence}\n{item.actionable_suggestion}"
        for item in accepted
    )
    for critique in accepted:
        path = critique.target_path
        parts = _segments(path)
        parent_path = "/" + "/".join(parts[:-1]) if len(parts) > 1 else path
        try:
            context = _get(original, parent_path)
        except ValueError:
            context = None
        local_content = _local_source(context, feedback_text)
        focus.append({
            "critique": critique.model_dump(mode="json"),
            "parent_path": parent_path,
            "parent_content": local_content,
            "editable_path_bases": _editable_path_bases(parent_path, local_content),
        })
    outcome: RewriteOutcome | None = None

    field_contracts = {
        "learning_objective": {
            "objective_id": "string, existing IDs must be preserved",
            "description": "non-empty string",
            "evidence_of_achievement": "string",
            "standard_refs": "string[]; never invent absent standards",
        },
        "lesson_question": {
            "question": "non-empty string",
            "expected_responses": "string[]",
            "possible_misconceptions": "string[]",
            "teacher_follow_ups": "string[]",
            "evidence_to_notice": "string",
        },
        "teaching_artifact": {
            "artifact_id": "unique non-empty string",
            "artifact_type": "non-empty string",
            "title": "non-empty string",
            "purpose": "string",
            "content": "non-empty, ready-to-use content",
            "answer_or_success_criteria": "string",
        },
        "procedure_step": {
            "step_id": "unique non-empty string",
            "stage": "non-empty string",
            "duration_minutes": "integer >= 1; total lesson time must stay unchanged",
            "objective_ids": "existing objective ID[]",
            "teacher_actions": "string[]",
            "student_actions": "string[]",
            "questions": "lesson_question[]",
            "assessment": "string",
            "design_rationale": "string",
            "resource_ids": "existing resource ID[]",
            "artifact_ids": "existing or concurrently-created artifact ID[]",
            "transition": "string",
            "student_product": "string",
            "success_criteria": "string[]",
            "scaffolds": "string[]",
            "extensions": "string[]",
            "response_branches": "{trigger, teacher_move, purpose}[]",
        },
    }

    def validate(proposal: PatchProposal) -> None:
        nonlocal outcome
        outcome = materialize_patch(
            proposal, version.document, accepted, task,
            duration_tolerance_minutes,
        )

    response = provider.invoke_structured(
        prompt=prompt,
        input_payload={
            "round_index": round_index,
            "lesson_identity": original["metadata"],
            "accepted_feedback_and_local_source": focus,
            "referenced_context": _referenced_objects(version.document, feedback_text),
            "lesson_structure": {
                "objectives": [{"id": item.objective_id, "description": item.description}
                               for item in version.document.learning_objectives],
                "steps": [{"index": index, "id": item.step_id,
                           "editable_path_base": f"/procedure_steps/{_path_token(item.step_id)}",
                           "stage": item.stage,
                           "duration_minutes": item.duration_minutes}
                          for index, item in enumerate(version.document.procedure_steps)],
                "artifacts": [{"id": item.artifact_id,
                               "editable_path_base": f"/teaching_artifacts/{_path_token(item.artifact_id)}"}
                              for item in version.document.teaching_artifacts],
                "resources": [{"id": item.resource_id,
                               "editable_path_base": f"/resources/{_path_token(item.resource_id)}"}
                              for item in version.document.resources],
                "artifact_ids": [item.artifact_id for item in version.document.teaching_artifacts],
                "resource_ids": [item.resource_id for item in version.document.resources],
            },
            "field_contracts": field_contracts,
            "task_constraints": task.class_constraints,
        },
        output_schema=PatchProposal,
        stage="rewrite_patch",
        result_validator=validate,
        # A schema-invalid local value (especially a newly added artifact or
        # question) is usually repairable from the validator feedback.  One
        # bounded retry is materially cheaper than abandoning the whole round.
        max_attempts=2,
        max_output_tokens=7168,
    )
    assert outcome is not None
    return AgentOutput(
        value=outcome, usage=response.usage,
        estimated_cost=response.estimated_cost, metadata=response.metadata,
    )


def incremental_patch_rewrite(
    provider: OpenAICompatibleProvider,
    task: LessonTask,
    version: LessonPlanVersion,
    accepted: list[CritiqueItem],
    round_index: int,
    duration_tolerance_minutes: int,
) -> AgentOutput[RewriteOutcome]:
    """Commit valid edits independently; one bad opinion cannot erase others.

    Each issue gets one bounded model call over the latest committed document.
    A failing patch is recorded as unresolved, while subsequent issues still
    get a chance. No changed version is returned unless at least one actual
    field changed and the edit introduces no new deterministic hard-rule
    regression. Pre-existing import defects may remain for later critiques.
    """
    working = version.document
    changes: list[RewriteChange] = []
    unresolved: list[str] = []
    reasons: dict[str, str] = {}
    usage = TokenUsage()
    cost = 0.0
    attempts = 0
    last_metadata: AgentCallMetadata | None = None
    for index, critique in enumerate(accepted):
        current = version.model_copy(update={"document": working})
        try:
            output = patch_rewrite(
                provider, task, current, [critique], round_index,
                duration_tolerance_minutes,
            )
        except ProviderInvocationError as exc:
            usage = TokenUsage(
                input_tokens=usage.input_tokens + exc.usage.input_tokens,
                output_tokens=usage.output_tokens + exc.usage.output_tokens,
            )
            cost += exc.estimated_cost
            attempts += exc.attempts
            unresolved.append(critique.critique_id)
            reasons[critique.critique_id] = f"局部修改未通过模型或结构校验：{exc}"
            # Auth, quota and connection failures will not be repaired by
            # spending more calls on the remaining opinions.
            if any(marker in str(exc).lower() for marker in (
                "authenticationerror", "permissiondeniederror", "insufficient_quota",
                "402", "401", "connectionerror", "apiconnectionerror",
            )):
                for remaining in accepted[index + 1:]:
                    unresolved.append(remaining.critique_id)
                    reasons[remaining.critique_id] = "上游模型服务不可用，未尝试付费调用"
                break
            continue
        usage = TokenUsage(
            input_tokens=usage.input_tokens + output.usage.input_tokens,
            output_tokens=usage.output_tokens + output.usage.output_tokens,
        )
        cost += output.estimated_cost
        attempts += output.metadata.attempts if output.metadata else 1
        last_metadata = output.metadata
        if output.value.changes:
            working = output.value.document
            changes.extend(output.value.changes)
        else:
            unresolved.append(critique.critique_id)
            reasons[critique.critique_id] = output.value.unresolved_reasons.get(
                critique.critique_id, "模型未提交任何可验证的内容修改",
            )

    if not changes:
        explanation = "; ".join(
            f"{critique_id}: {reason[:220]}" for critique_id, reason in reasons.items()
        )
        raise ProviderInvocationError(
            "no effective lesson-plan edit; " + explanation[:1200],
            attempts=attempts, usage=usage, estimated_cost=cost,
        )
    if last_metadata is None:
        raise AssertionError("committed edits require model call metadata")
    return AgentOutput(
        value=RewriteOutcome(
            document=working,
            changes=changes,
            unresolved_critique_ids=unresolved,
            unresolved_reasons=reasons,
        ),
        usage=usage,
        estimated_cost=cost,
        metadata=replace(last_metadata, attempts=attempts),
    )
