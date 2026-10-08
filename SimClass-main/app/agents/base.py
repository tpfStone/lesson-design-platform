"""BaseAgent —— 所有课堂 Agent 的统一基类。

不同角色 = 同一个 LLM + 不同的 system prompt（不部署独立模型）。
Interaction functions 是 MVP 的工程实现，不是论文公开代码中的固定 API。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..controller.state import ClassState

# Interaction Functions 的通用指令模板
FUNCTION_INSTRUCTIONS = {
    "answer_question": "[answer_question] 请回答课堂上最新提出的问题，紧扣当前学习材料，讲解清晰。",
    "ask_question": "[ask_question] 请围绕当前学习材料提出一个有价值的课堂问题，促进大家思考。",
    "elaborate": "[elaborate] 请对刚才讲授或讨论的概念做进一步深入解释，可以举例说明。",
    "summarize": "[summarize] 请简要总结目前课堂已经讲授的关键内容，条理清晰。",
    "encourage": "[encourage] 请以同伴/助教的身份真诚地鼓励情绪低落的学习者，给予情感支持，不要说教。",
    "discuss": "[discuss] 若教师刚提出问题，请先给出你自己的回答或思路；否则围绕当前材料分享观点，参与讨论。不要声称其他人已经回答。",
    "redirect": "[redirect] 请用友好幽默的方式把跑题的同学拉回到当前学习材料上。",
}


class BaseAgent:
    name: str = "base"
    display_name: str = "BASE"
    system_prompt: str = "You are a classroom agent."
    allowed_functions: list[str] = list(FUNCTION_INSTRUCTIONS.keys())

    def __init__(self, llm):
        self.llm = llm

    # ---------- prompt 构建 ----------

    def build_messages(self, state: "ClassState", instruction: str) -> list[dict]:
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self._build_context(state) + "\n\n任务:\n" + instruction},
        ]

    def _build_context(self, state: "ClassState") -> str:
        lines = ["[课堂上下文]"]
        m = state.current_material
        if m:
            taught = "已讲授" if state.current_material_taught else "尚未讲授"
            lines.append(f"当前材料: {m['title']}（{taught}）")
            lines.append(f"教学脚本: {m.get('teaching_script', '')}")
            if m.get("student_task"):
                lines.append(f"学生任务与产出: {m['student_task']}")
            if m.get("evaluation_control"):
                lines.append(f"评价与调控: {m['evaluation_control']}")
            if m.get("key_points"):
                lines.append("关键要点: " + "；".join(m["key_points"]))
        else:
            lines.append("所有材料已全部讲授完毕。")
        if state.dialogue_history:
            lines.append("最近课堂对话:")
            for e in state.recent_dialogue(8):
                lines.append(f"[{e.speaker}] ({e.function}): {e.content}")
        if state.pending_user_message:
            lines.append(f"用户最新消息: {state.pending_user_message}")
        return "\n".join(lines)

    def _respond(self, state: "ClassState", instruction: str) -> str:
        messages = self.build_messages(state, instruction)
        return self.llm.chat(messages).strip()

    # ---------- Interaction Functions (所有适合的 Agent 可用) ----------

    def answer_question(self, state: "ClassState") -> str:
        return self._respond(state, FUNCTION_INSTRUCTIONS["answer_question"])

    def ask_question(self, state: "ClassState") -> str:
        return self._respond(state, FUNCTION_INSTRUCTIONS["ask_question"])

    def elaborate(self, state: "ClassState") -> str:
        return self._respond(state, FUNCTION_INSTRUCTIONS["elaborate"])

    def summarize(self, state: "ClassState") -> str:
        return self._respond(state, FUNCTION_INSTRUCTIONS["summarize"])

    def encourage(self, state: "ClassState") -> str:
        return self._respond(state, FUNCTION_INSTRUCTIONS["encourage"])

    def discuss(self, state: "ClassState") -> str:
        return self._respond(state, FUNCTION_INSTRUCTIONS["discuss"])

    def redirect(self, state: "ClassState") -> str:
        return self._respond(state, FUNCTION_INSTRUCTIONS["redirect"])
