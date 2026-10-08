"""FunctionExecutor —— 校验权限并执行 Agent function，把结果写入 ClassState。"""
from __future__ import annotations

from ..agents.base import BaseAgent
from .state import ClassState, DialogueEntry, ManagerDecision


class InvalidActionError(ValueError):
    """Manager 决策非法（未知角色 / 无权限 / 状态不允许）。"""


class FunctionExecutor:
    def __init__(self, agents: dict[str, BaseAgent]):
        self.agents = agents

    def execute(self, decision: ManagerDecision, state: ClassState) -> DialogueEntry:
        """执行 speaker 的 function 并更新 ClassState。

        ManagerDecision(speaker="assistant", function="answer_question")
            -> agents["assistant"].answer_question(state)
            -> 结果写入 dialogue_history
        """
        agent = self.agents.get(decision.speaker)
        if agent is None:
            raise InvalidActionError(f"未知 speaker: {decision.speaker}")
        if decision.speaker not in state.active_roles:
            raise InvalidActionError(
                f"{decision.speaker} 不在本节课参与角色(active_roles)中"
            )
        if decision.function not in agent.allowed_functions:
            raise InvalidActionError(
                f"{decision.speaker} 无权执行 function: {decision.function}"
            )
        if decision.function in ("teach", "next_material") and state.current_material is None:
            raise InvalidActionError(f"所有材料已讲完，不能执行 {decision.function}")

        # next_material: 先推进材料，这样 Agent 生成的过渡语可以引用新材料
        if decision.function == "next_material":
            state.advance_section()

        method = getattr(agent, decision.function, None)
        if method is None:
            raise InvalidActionError(
                f"agent {decision.speaker} 未实现 function: {decision.function}"
            )
        content = method(state)

        if decision.function == "teach":
            state.mark_taught()

        entry = DialogueEntry(
            speaker=decision.speaker, function=decision.function, content=content
        )
        state.add_entry(entry)
        return entry
