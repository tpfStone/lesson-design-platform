"""测试辅助: 按脚本依次返回预设回复的假 LLM。"""
from app.llm.mock import MockProvider


class ScriptedLLM(MockProvider):
    """用于确定性测试 Manager / Agent 行为。"""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def chat(self, messages, temperature=0.7):
        self.calls.append(messages)
        if not self.responses:
            return "(no scripted response)"
        return self.responses.pop(0)
