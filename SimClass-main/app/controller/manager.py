"""Manager Agent —— 隐藏的 meta-agent。

它不能直接回答用户问题，唯一职责:
    根据当前 Class State 决定下一步由哪个 Agent 执行哪个 Function。

核心 decision 由 Manager LLM 完成；JSON schema 校验 / 权限校验 / fallback
只作为 validation 与 guardrail，防止程序崩溃。
"""
from __future__ import annotations

import json
import re
from typing import Optional

from ..agents.base import BaseAgent
from .state import ClassState, ManagerDecision

MANAGER_SYSTEM_PROMPT = """你是 SimClass 虚拟课堂中隐藏的 Manager（meta-agent）。
你自己绝不直接回答用户问题，你只负责编排课堂流程:
根据当前 Class State 决定下一步由哪个 Agent 执行哪个 Function。

本节课参与角色(active_roles):
{active_roles}

可用 Agent 及其有权执行的 function（仅限 active_roles 内）:
{agent_functions}

每轮的触发来源(trigger_type):
initialization=课堂刚开始; user_input=用户刚发言(优先回应用户);
empty_enter=用户按回车示意继续; timeout=用户超时未输入(课堂自主推进，
可继续教学/推进材料/让同学提问或总结)。

决策原则:
1. 课堂刚开始 / 新材料尚未讲授 -> teacher 执行 teach。
2. 用户提出问题 -> 优先 teacher 或 assistant 执行 answer_question；
   需要更深入视角时可让 deep_thinker / inquisitive_mind 参与 discuss 或 ask_question，
   但不要每次都动员所有 Agent，保持自然节奏。
3. 概念刚讲完 -> 可让合适的 classmate ask_question 或 discuss 活跃气氛。
4. 用户情绪低落（觉得太难、想放弃）-> assistant 或合适的 classmate 执行 encourage，
   提供非教师式的同伴支持。
5. 用户明显跑题或干扰课堂 -> class_clown 或 assistant 执行 redirect，
   之后应回到 teacher 继续当前材料。
6. 当前材料讲授且讨论充分 -> teacher 执行 next_material。
7. 所有材料讲完 -> note_taker（若参与）执行 summarize 收尾（否则由 teacher summarize），随后设置 end_class=true。
8. 课堂按教案的教学环节顺序推进；当前环节的教师活动、学生任务与评价要求
   都是本轮上下文，只有 next_material 才能进入下一教学环节。
9. 教师提出需要学生回答的问题后，先让已选的学生角色实际发言，不能把教师的
   设问或假想回答当成学生已经作答。若本节选了学生角色，结束前至少有一次
   学生实际发言；若选了 assistant，结束前让助教做一次有意义的释疑或支持。

硬性约束: speaker 必须从本节课参与角色(active_roles)中选择，
禁止选择未参与角色。

必须避免: agent spam（连续多个无意义发言）、重复回答同一问题、无休止讨论、
classmate 抢走 teacher 的教学职责（classmate 不能 teach / next_material）。

只输出严格合法的 JSON，不要输出其他任何内容:
{{"speaker": "...", "function": "...", "reason": "...", "end_class": false}}
"""


class Manager:
    def __init__(self, llm, agents: dict[str, BaseAgent]):
        self.llm = llm
        self.agents = agents

    # ---------- 决策 ----------

    def decide(self, state: ClassState, feedback: Optional[str] = None) -> ManagerDecision:
        messages = [
            {"role": "system", "content": self._system_prompt(state)},
            {"role": "user", "content": self._build_brief(state)},
        ]
        if feedback:
            messages.append({"role": "user", "content": feedback})

        last_error = "no output"
        for _ in range(3):  # 非法 JSON / 非法决策 -> retry
            raw = self.llm.chat(messages, temperature=0.2)
            decision, err = self._parse_and_validate(raw, state)
            if decision is not None:
                return decision
            last_error = err
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"你的输出无效（{err}）。请重新输出严格合法的 JSON。"})

        return self._fallback(state, last_error)

    # ---------- prompt ----------

    def _system_prompt(self, state: ClassState) -> str:
        active_agents = [self.agents[r] for r in state.active_roles if r in self.agents]
        lines = [f"- {a.name}: {', '.join(a.allowed_functions)}" for a in active_agents]
        return (MANAGER_SYSTEM_PROMPT
                .replace("{active_roles}", ", ".join(state.active_roles))
                .replace("{agent_functions}", "\n".join(lines)))

    def _build_brief(self, state: ClassState) -> str:
        lines = ["[课堂状态]"]
        total = len(state.materials)
        lines.append(f"课程进度: {min(state.material_index, total)}/{total}")
        m = state.current_material
        if m:
            lines.append(f"当前材料: {m['title']}")
            lines.append(f"当前材料已讲授: {'yes' if state.current_material_taught else 'no'}")
            if m.get("teaching_script"):
                lines.append(f"教学脚本摘要: {m['teaching_script'][:200]}")
            if m.get("duration_minutes") is not None:
                lines.append(f"环节时长: {m['duration_minutes']} 分钟")
            if m.get("student_task"):
                lines.append(f"学生任务与产出: {m['student_task'][:200]}")
            if m.get("evaluation_control"):
                lines.append(f"评价与调控: {m['evaluation_control'][:120]}")
        else:
            lines.append("当前材料: 无（全部讲完）")
            lines.append("当前材料已讲授: no")
        lines.append("已完成材料: " + ("、".join(state.taught_materials) if state.taught_materials else "无"))
        lines.append("剩余材料: " + ("、".join(state.remaining_materials) if state.remaining_materials else "无"))
        lines.append(f"所有材料已完成: {'yes' if state.all_materials_finished else 'no'}")
        if state.last_speaker:
            lines.append(f"上一发言: {state.last_speaker} / {state.last_function}")
        else:
            lines.append("上一发言: 无")
        lines.append(f"本轮触发(trigger_type): {state.last_trigger_type}")
        if state.consecutive_timeout_count:
            lines.append(f"连续超时自主推进轮数(consecutive_timeout_count): "
                         f"{state.consecutive_timeout_count}")
        lines.append("本节课参与角色(active_roles): " + ", ".join(state.active_roles))
        speakers = {entry.speaker for entry in state.dialogue_history}
        if self._student_roles(state):
            lines.append("学生已实际发言: " +
                         ("yes" if speakers.intersection(self._student_roles(state)) else "no"))
        if "assistant" in state.active_roles:
            lines.append("助教已实际参与: " + ("yes" if "assistant" in speakers else "no"))
        if self._unanswered_teacher_question(state):
            lines.append("教师最近的问题仍待学生实际回应: yes")

        if state.dialogue_history:
            lines.append("[最近课堂对话]")
            for e in state.recent_dialogue(8):
                lines.append(f"[{e.speaker}] ({e.function}): {e.content}")
        if state.pending_user_message:
            lines.append(f"用户最新消息: {state.pending_user_message}")

        lines.append("请决定课堂下一步，输出 JSON。")
        return "\n".join(lines)

    # ---------- 输出校验 (validation / safety / guardrails) ----------

    def _parse_and_validate(self, raw: str, state: ClassState):
        text = raw.strip()
        # 剥离 markdown code fence / 提取首个 JSON 对象
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
        if m:
            text = m.group(1)
        else:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end > start:
                text = text[start:end + 1]
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None, "不是合法 JSON"

        speaker = data.get("speaker")
        function = data.get("function")
        if not speaker or not function:
            return None, "缺少 speaker 或 function"

        agent = self.agents.get(speaker)
        if agent is None:
            return None, f"未知 speaker: {speaker}"
        if speaker not in state.active_roles:
            return None, (f"{speaker} 不在本节课参与角色(active_roles)中，"
                          f"只能从 {state.active_roles} 中选择")
        if function not in agent.allowed_functions:
            return None, f"{speaker} 无权执行 {function}"
        if function in ("teach", "next_material") and state.current_material is None:
            return None, "所有材料已讲完，不能再 teach / next_material"
        if function == "next_material":
            if not state.current_material_taught:
                return None, "当前教学环节尚未由教师讲授，不能直接进入下一环节"
            if self._unanswered_teacher_question(state):
                return None, "教师已提出问题，请先让已选学生角色实际回应，再进入下一环节"
            if state.material_index == len(state.materials) - 1:
                missing = self._missing_participation(state)
                if missing:
                    return None, f"课堂收尾前仍缺少 {missing} 的实际参与"
        if data.get("end_class") and not state.all_materials_finished:
            return None, "尚有未完成的教学环节，不能提前宣布下课"

        decision = ManagerDecision(
            speaker=speaker,
            function=function,
            reason=str(data.get("reason", "")),
            end_class=bool(data.get("end_class", False)),
        )
        return decision, None

    @staticmethod
    def _student_roles(state: ClassState) -> list[str]:
        return [role for role in state.active_roles
                if role not in {"teacher", "assistant", "note_taker"}]

    def _missing_participation(self, state: ClassState) -> str | None:
        speakers = {entry.speaker for entry in state.dialogue_history}
        if self._student_roles(state) and not speakers.intersection(self._student_roles(state)):
            return "学生"
        if "assistant" in state.active_roles and "assistant" not in speakers:
            return "助教"
        return None

    def _unanswered_teacher_question(self, state: ClassState) -> bool:
        if not self._student_roles(state):
            return False
        last_question = max((index for index, entry in enumerate(state.dialogue_history)
                             if entry.speaker == "teacher" and any(mark in entry.content for mark in ("？", "?"))),
                            default=-1)
        last_student = max((index for index, entry in enumerate(state.dialogue_history)
                            if entry.speaker in self._student_roles(state)), default=-1)
        return last_question > last_student

    # ---------- fallback guardrail（仅在 LLM 持续输出非法决策时触发）----------

    def _fallback(self, state: ClassState, err: str) -> ManagerDecision:
        if state.current_material is None:
            return ManagerDecision("teacher", "summarize",
                                   f"fallback（{err}）: 所有材料已讲完，总结并下课", True)
        if state.pending_user_message:
            return ManagerDecision("teacher", "answer_question",
                                    f"fallback（{err}）: 兜底回答用户问题")
        if not state.current_material_taught:
            return ManagerDecision("teacher", "teach", f"fallback（{err}）: 开始教学")
        if self._unanswered_teacher_question(state) or (
                state.material_index == len(state.materials) - 1
                and self._missing_participation(state) == "学生"):
            learner = self._student_roles(state)[0]
            return ManagerDecision(learner, "discuss", f"fallback（{err}）: 回应教师的课堂提问")
        if (state.material_index == len(state.materials) - 1
                and self._missing_participation(state) == "助教"):
            return ManagerDecision("assistant", "elaborate", f"fallback（{err}）: 助教补充说明")
        return ManagerDecision("teacher", "next_material", f"fallback（{err}）: 继续课程")
