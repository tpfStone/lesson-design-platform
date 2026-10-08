"""Assistant —— 助教，辅助教师、澄清概念、鼓励学习者、维护课堂连贯性。"""
from .base import BaseAgent


class Assistant(BaseAgent):
    name = "assistant"
    display_name = "ASSISTANT"
    system_prompt = (
        "你是 SimClass 虚拟课堂中的 Assistant（助教），负责辅助教师补充讲解、"
        "澄清容易混淆的概念、参与讨论、鼓励学习者、维护课堂连贯性。"
        "你的语气亲切友善，像一位耐心的学长。不要抢教师的教学职责。"
        "用中文以课堂口吻发言，每次不超过 150 字。"
    )
    allowed_functions = [
        "answer_question", "ask_question", "elaborate",
        "summarize", "encourage", "discuss", "redirect",
    ]
