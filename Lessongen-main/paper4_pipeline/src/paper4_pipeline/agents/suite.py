"""Runtime-independent container for the Paper#4 agent responsibilities."""

from __future__ import annotations

from dataclasses import dataclass

from paper4_pipeline.agents.protocols import (
    CriticAgent,
    DesignArchitectAgent,
    JudgeAgent,
    RewriterAgent,
    ValidatorAgent,
    WriterAgent,
)
from paper4_pipeline.domain.models import AgentProfile


@dataclass(frozen=True)
class AgentSuite:
    execution_mode: str
    profiles: dict[str, AgentProfile]
    designer: DesignArchitectAgent
    writer: WriterAgent
    critics: list[CriticAgent]
    validator: ValidatorAgent
    judge: JudgeAgent
    rewriter: RewriterAgent
