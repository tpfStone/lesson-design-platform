"""Typed ports between orchestration code and replaceable agent backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

from paper4_pipeline.domain.models import (
    CritiqueBatch,
    CritiqueItem,
    EvaluationReport,
    KnowledgeBundle,
    LessonDesignBlueprint,
    LessonPlanDocument,
    LessonPlanVersion,
    LessonTask,
    RewriteOutcome,
    TokenUsage,
    ValidationBatch,
)


T = TypeVar("T")


@dataclass(frozen=True)
class AgentCallMetadata:
    provider: str
    model_name: str
    prompt_id: str
    prompt_version: str
    prompt_sha256: str
    response_id: str = ""
    finish_reason: str = ""
    attempts: int = 1
    thinking_mode: str = "disabled"


@dataclass(frozen=True)
class AgentOutput(Generic[T]):
    """A model result plus auditable usage metadata."""

    value: T
    usage: TokenUsage = field(default_factory=TokenUsage)
    estimated_cost: float = 0.0
    metadata: AgentCallMetadata | None = None


class WriterAgent(Protocol):
    profile_id: str

    def generate(
        self,
        task: LessonTask,
        knowledge: KnowledgeBundle | None = None,
        blueprint: LessonDesignBlueprint | None = None,
    ) -> AgentOutput[LessonPlanDocument]: ...


class DesignArchitectAgent(Protocol):
    profile_id: str

    def design(
        self,
        task: LessonTask,
        knowledge: KnowledgeBundle | None = None,
    ) -> AgentOutput[LessonDesignBlueprint]: ...


class CriticAgent(Protocol):
    profile_id: str

    def review(
        self,
        task: LessonTask,
        version: LessonPlanVersion,
        round_index: int,
        knowledge: KnowledgeBundle | None = None,
        prior_critiques: list[CritiqueItem] | None = None,
    ) -> AgentOutput[CritiqueBatch]: ...


class ValidatorAgent(Protocol):
    profile_id: str

    def validate(
        self,
        task: LessonTask,
        version: LessonPlanVersion,
        critiques: CritiqueBatch,
        round_index: int,
        knowledge: KnowledgeBundle | None = None,
    ) -> AgentOutput[ValidationBatch]: ...


class JudgeAgent(Protocol):
    profile_id: str

    def evaluate(
        self,
        task: LessonTask,
        version: LessonPlanVersion,
        unresolved_issue_count: int,
        knowledge: KnowledgeBundle | None = None,
    ) -> AgentOutput[EvaluationReport]: ...


class RewriterAgent(Protocol):
    profile_id: str

    def rewrite(
        self,
        task: LessonTask,
        version: LessonPlanVersion,
        accepted_critiques: list[CritiqueItem],
        round_index: int,
        knowledge: KnowledgeBundle | None = None,
    ) -> AgentOutput[RewriteOutcome]: ...
