"""LLM Provider 抽象基类。"""
from abc import ABC, abstractmethod


class LLMError(RuntimeError):
    """LLM 调用失败（网络 / 响应格式等）。"""


class BaseLLMProvider(ABC):
    """统一的 chat 接口，所有 Agent 和 Manager 共用。"""
    name = "base"

    @abstractmethod
    def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        """messages: [{"role": "system"|"user"|"assistant", "content": "..."}] -> str"""
        raise NotImplementedError
