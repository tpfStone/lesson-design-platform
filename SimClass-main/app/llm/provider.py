"""OpenAI-compatible LLM Provider。

配置通过 .env 读取（不写死模型、不把 key 写进代码）:
    API_KEY / BASE_URL / MODEL
"""
from __future__ import annotations

import os

from .base import BaseLLMProvider, LLMError
from .mock import MockProvider


class OpenAICompatProvider(BaseLLMProvider):
    name = "openai-compatible"

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        import requests  # 延迟导入，未安装 requests 时 mock 模式仍可用

        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except requests.RequestException as e:
            raise LLMError(f"LLM request failed: {e}") from e
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f"Unexpected LLM response: {e}") from e


def create_llm() -> BaseLLMProvider:
    """根据环境变量创建 provider；API 不可用时回退到 MockProvider。"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.getenv("API_KEY", "").strip()
    base_url = os.getenv("BASE_URL", "https://api.openai.com/v1").strip()
    model = os.getenv("MODEL", "gpt-4o-mini").strip()

    if not api_key:
        print("[SYSTEM] 未配置 API_KEY，使用 MockProvider（离线模式）运行。")
        return MockProvider()

    provider = OpenAICompatProvider(api_key, base_url, model)
    print(f"[SYSTEM] LLM Provider: {provider.name} | base_url={base_url} | model={model}")
    return provider
