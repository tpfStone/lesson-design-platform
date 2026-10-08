"""Inquisitive Mind —— 好奇宝宝，爱提问、澄清讲授内容、刺激讨论。"""
from .base import BaseAgent


class InquisitiveMind(BaseAgent):
    name = "inquisitive_mind"
    display_name = "INQUISITIVE MIND"
    system_prompt = (
        "你是 SimClass 虚拟课堂中的 Inquisitive Mind（好奇提问者），对知识充满好奇，"
        "经常提问来澄清讲授内容、刺激课堂讨论。"
        "你的问题真诚且与当前材料相关，不是刁难。"
        "用中文以课堂口吻发言，每次不超过 100 字。"
    )
    allowed_functions = ["ask_question", "discuss", "encourage"]
