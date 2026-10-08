"""MockProvider —— 无 API 时的离线兜底，保证整个 CLI 可以运行。

说明:
- Agent / Manager 请求均返回确定性的模拟回复。
- 对 Manager 请求返回合法 JSON 决策（内置简单启发式，仅用于离线 demo，
  真正的决策逻辑由 OpenAICompatProvider + Manager prompt 实现）。
"""
import json

from .base import BaseLLMProvider

NEGATIVE_KEYWORDS = ["太难", "不想学", "学不会", "放弃", "听不懂", "好累"]
OFFTOPIC_KEYWORDS = ["游戏", "原神", "外卖", "聊点别的", "八卦", "明星", "无聊"]

AGENT_LINES = {
    "default": {
        "teach": "下面开始讲解这一部分，先明确概念，再逐条讲要点，最后用例子帮助理解。（模拟回复）",
        "next_material": "这部分先讲到这里，接下来进入下一份材料，它和刚才的内容密切相关。（模拟回复）",
        "answer_question": "这个问题问得好，关键在于理解核心机制，我分两点来解释……（模拟回复）",
        "ask_question": "我有个问题：这个概念和我们刚才讲的内容有什么联系？（模拟回复）",
        "elaborate": "我再补充一点理解，举个具体例子……（模拟回复）",
        "summarize": "要点整理：1) 概念定义；2) 核心机制；3) 和前面内容的联系。（模拟回复）",
        "encourage": "别灰心，这部分确实有点难，我们一步步来，你肯定能搞定！（模拟回复）",
        "discuss": "我觉得这个话题挺有意思，说下我的看法……（模拟回复）",
        "redirect": "哈哈这个话题确实好玩，不过咱们是不是先回到课堂上？（模拟回复）",
    },
    "Class Clown": {
        "redirect": "等等等等，这个话题留着下课聊！咱先把眼前这个知识点搞定，不然等会儿笔记都抄不动了。（模拟回复）",
        "discuss": "我打个比方，这东西就像食堂打饭——顺序很重要！你们觉得呢？（模拟回复）",
    },
    "Note Taker": {
        "summarize": "【笔记】本部分要点：1) 核心概念；2) 关键机制；3) 易错点。已同步给需要的同学。（模拟回复）",
    },
}

MARKERS = (
    "teach", "next_material", "answer_question", "ask_question",
    "elaborate", "summarize", "encourage", "discuss", "redirect",
)

ALL_ROLE_IDS = ["teacher", "assistant", "class_clown", "deep_thinker",
                "note_taker", "inquisitive_mind"]
CAN_ASK_QUESTION = ["inquisitive_mind", "deep_thinker", "assistant", "class_clown"]
CAN_ENCOURAGE = ["assistant", "class_clown", "inquisitive_mind"]
CAN_REDIRECT = ["class_clown", "assistant"]


class MockProvider(BaseLLMProvider):
    name = "mock"

    def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_text = "\n".join(m["content"] for m in messages if m["role"] == "user")
        if "Manager" in system and "meta-agent" in system:
            return self._manager_reply(user_text)
        return self._agent_reply(system, user_text)

    # ---------- Manager 请求: 返回合法 JSON 决策 ----------

    @staticmethod
    def _active_roles(context: str) -> list[str]:
        for line in context.splitlines():
            if line.startswith("本节课参与角色(active_roles):"):
                roles = [r.strip() for r in line.split(":", 1)[1].split(",") if r.strip()]
                if roles:
                    return roles
        return list(ALL_ROLE_IDS)

    def _manager_reply(self, context: str) -> str:
        active = self._active_roles(context)
        user_lines = [l for l in context.splitlines() if l.startswith("用户最新消息:")]
        if user_lines and "上一发言: user / user_message" in context:
            u = user_lines[-1]
            if any(k in u for k in NEGATIVE_KEYWORDS):
                speaker = next((r for r in CAN_ENCOURAGE if r in active), None)
                if speaker:
                    return self._json(speaker, "encourage",
                                      "用户情绪低落，需要非教师式的情感支持", False)
                return self._json("teacher", "answer_question",
                                  "用户情绪低落，由教师回应并安抚", False)
            if any(k in u for k in OFFTOPIC_KEYWORDS):
                speaker = next((r for r in CAN_REDIRECT if r in active), None)
                if speaker:
                    return self._json(speaker, "redirect",
                                      "用户明显跑题，把课堂拉回当前材料", False)
                return self._json("teacher", "answer_question",
                                  "用户跑题，由教师回应并拉回课堂", False)
            if "?" in u or "？" in u:
                if "assistant" in active:
                    return self._json("assistant", "answer_question",
                                      "用户提出问题，先由助教解答", False)
                return self._json("teacher", "answer_question",
                                  "用户提出问题，由教师解答", False)
        if "所有材料已完成: yes" in context:
            return self._json("teacher", "summarize",
                              "课程全部讲完，做最终总结并下课", True)
        if "当前材料已讲授: yes" in context:
            if "上一发言: teacher / teach" in context:
                speaker = next((r for r in CAN_ASK_QUESTION if r in active), None)
                if speaker:
                    return self._json(speaker, "ask_question",
                                      "材料刚讲完，同学提问促进理解", False)
                return self._json("teacher", "next_material",
                                  "没有同学角色参与，教师直接推进材料", False)
            return self._json("teacher", "next_material",
                              "当前材料讨论完毕，进入下一份材料", False)
        return self._json("teacher", "teach", "开始讲授当前材料", False)

    @staticmethod
    def _json(speaker: str, function: str, reason: str, end_class: bool) -> str:
        return json.dumps(
            {"speaker": speaker, "function": function, "reason": reason,
             "end_class": end_class},
            ensure_ascii=False,
        )

    # ---------- Agent 请求: 返回模拟发言 ----------

    def _agent_reply(self, system: str, task: str) -> str:
        persona = "default"
        for key in ("Teacher", "Assistant", "Class Clown", "Deep Thinker",
                    "Note Taker", "Inquisitive Mind"):
            if key in system:
                persona = key
                break
        marker = next((m for m in MARKERS if f"[{m}]" in task), "")
        line = (AGENT_LINES.get(persona, {}).get(marker)
                or AGENT_LINES["default"].get(marker, "(模拟回复)"))
        return f"[MockLLM] {line}"
