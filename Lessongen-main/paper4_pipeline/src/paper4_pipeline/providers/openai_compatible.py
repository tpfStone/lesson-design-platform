"""DeepSeek's OpenAI-compatible structured-output adapter.

This module is deliberately the only place that reads an API key.  The key is
never copied into graph state, traces, prompts, or exported artifacts.
"""

from __future__ import annotations

import json
import asyncio
import re
import os
import hashlib
from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Generic, TypeVar
from uuid import uuid4

from dotenv import find_dotenv, load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from paper4_pipeline.agents.prompts import PromptSpec
from paper4_pipeline.agents.protocols import AgentCallMetadata
from paper4_pipeline.domain.models import ModelCallAttempt, ModelConfig, TokenUsage
from paper4_pipeline.observability.call_ledger import current_ledger


T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class ProviderCallResult(Generic[T]):
    value: T
    usage: TokenUsage
    estimated_cost: float
    metadata: AgentCallMetadata


class ProviderInvocationError(RuntimeError):
    """A failed real invocation carrying non-secret accounting metadata."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        usage: TokenUsage,
        estimated_cost: float,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.usage = usage
        self.estimated_cost = estimated_cost


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return str(content or "")


def _json_object(text: str) -> object:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].strip().lower() in {"```", "```json"}:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    if not candidate:
        raise ValueError("model returned empty content")
    return json.loads(candidate)


def _usage_from_message(message: object) -> TokenUsage:
    raw = getattr(message, "usage_metadata", None) or {}
    response_meta = getattr(message, "response_metadata", None) or {}
    token_usage = response_meta.get("token_usage", {})
    input_tokens = int(
        raw.get("input_tokens")
        or raw.get("prompt_tokens")
        or token_usage.get("prompt_tokens")
        or 0
    )
    output_tokens = int(
        raw.get("output_tokens")
        or raw.get("completion_tokens")
        or token_usage.get("completion_tokens")
        or 0
    )
    return TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)


def _message_reports_usage(message: object) -> bool:
    raw = getattr(message, "usage_metadata", None) or {}
    response_meta = getattr(message, "response_metadata", None) or {}
    token_usage = response_meta.get("token_usage") or {}
    return any(
        key in raw for key in ("input_tokens", "output_tokens", "prompt_tokens", "completion_tokens")
    ) or any(key in token_usage for key in ("prompt_tokens", "completion_tokens"))


class CallLedgerWriteError(RuntimeError):
    """The model returned, but its paid attempt could not be audited safely."""


def _is_non_retryable_error(exc: Exception) -> bool:
    """Identify failures that another identical paid attempt cannot repair."""

    if type(exc).__name__ in {
        "AuthenticationError",
        "PermissionDeniedError",
        "BadRequestError",
        "NotFoundError",
    }:
        return True
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
    return status_code in {400, 401, 402, 403, 404, 422}


class OpenAICompatibleProvider:
    """One role-scoped DeepSeek client with validated JSON output."""

    def __init__(self, settings: ModelConfig) -> None:
        self.settings = settings
        self._client: ChatOpenAI | None = None

    @staticmethod
    def load_environment() -> None:
        path = find_dotenv(usecwd=True)
        if path:
            load_dotenv(path, override=False)

    def configuration_summary(self) -> dict[str, object]:
        self.load_environment()
        return {
            "provider": self.settings.provider,
            "model_name": self.settings.model_name,
            "base_url": os.getenv(
                self.settings.base_url_env, self.settings.base_url_default
            ),
            "api_key_env": self.settings.api_key_env,
            "api_key_present": bool(os.getenv(self.settings.api_key_env, "").strip()),
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "timeout_seconds": self.settings.timeout_seconds,
            "max_retries": self.settings.max_retries,
            "thinking_mode": self.settings.thinking_mode,
            "reasoning_effort": self.settings.reasoning_effort,
        }

    def _get_client(self) -> ChatOpenAI:
        if self._client is not None:
            return self._client
        self.load_environment()
        api_key = os.getenv(self.settings.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(
                f"missing API key: set {self.settings.api_key_env} in the process "
                "environment or repository .env"
            )
        base_url = os.getenv(
            self.settings.base_url_env, self.settings.base_url_default
        ).strip()
        if not base_url:
            raise RuntimeError(
                f"empty base URL: set {self.settings.base_url_env} or use the default"
            )
        kwargs: dict[str, object] = {
            "model": self.settings.model_name,
            "api_key": api_key,
            "base_url": base_url,
            "timeout": self.settings.timeout_seconds,
            # Retries are owned here so attempts and parse failures are auditable.
            "max_retries": 0,
            "extra_body": {
                "thinking": {"type": self.settings.thinking_mode},
                # langchain-openai 1.x sends this extra_body verbatim to
                # completions.parse(), and the openai SDK unfolds it into the
                # top-level HTTP body, so DeepSeek receives max_tokens=... as
                # requested. Do NOT pass max_tokens as a ChatOpenAI constructor
                # argument: that path is renamed to max_completion_tokens and
                # DeepSeek ignores it (silent 8K default).
                "max_tokens": self.settings.max_tokens,
            },
        }
        if self.settings.thinking_mode == "disabled":
            kwargs["temperature"] = self.settings.temperature
        else:
            kwargs["reasoning_effort"] = self.settings.reasoning_effort
        self._client = ChatOpenAI(**kwargs)
        return self._client

    def invoke_structured(
        self,
        *,
        prompt: PromptSpec,
        input_payload: dict[str, object],
        output_schema: type[T],
        stage: str,
        result_validator: Callable[[T], None] | None = None,
        max_attempts: int | None = None,
        max_output_tokens: int | None = None,
    ) -> ProviderCallResult[T]:
        """Call the real model, parse JSON, and validate the full Pydantic contract."""

        if max_attempts is not None and max_attempts < 1:
            raise ValueError("max_attempts must be positive")

        client = self._get_client()
        schema = output_schema.model_json_schema()
        system = (
            f"{prompt.content}\n\n"
            "## 运行时强制输出契约\n"
            "最终响应必须且只能是一个 JSON object；不要 Markdown 代码块，不要解释，"
            "不要输出思维链。字段必须满足下方 JSON Schema。若信息不足，请在合法字段"
            "中保守表达，不得杜撰来源。\n"
            f"JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"
        )
        base_input = (
            f"stage={stage}\n"
            "下面是唯一可信的运行输入。请按系统提示完成职责并返回 JSON。\n"
            f"INPUT_JSON:\n{json.dumps(input_payload, ensure_ascii=False)}"
        )
        total_usage = TokenUsage()
        last_error = "unknown error"
        correction = ""
        previous_invalid_output = ""
        attempts_made = 0
        allowed_attempts = max_attempts or self.settings.max_retries + 1
        call_id = uuid4().hex
        config_sha256 = hashlib.sha256(
            self.settings.model_dump_json().encode("utf-8")
        ).hexdigest()
        rate_id = hashlib.sha256(
            json.dumps({
                "model": self.settings.model_name,
                "input_per_million": self.settings.input_cost_per_million,
                "output_per_million": self.settings.output_cost_per_million,
            }, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        for attempt in range(1, allowed_attempts + 1):
            attempts_made = attempt
            attempt_started = perf_counter()
            attempt_usage: TokenUsage | None = None
            usage_source = "unknown"
            finish_reason = ""
            messages = [
                SystemMessage(content=system),
                HumanMessage(content=base_input),
            ]
            if correction:
                if previous_invalid_output:
                    messages.append(AIMessage(content=previous_invalid_output))
                messages.append(HumanMessage(content=correction))
            try:
                bind_options: dict[str, object] = {
                    "response_format": {"type": "json_object"},
                }
                if max_output_tokens is not None:
                    bind_options["extra_body"] = {
                        "thinking": {"type": self.settings.thinking_mode},
                        "max_tokens": max_output_tokens,
                    }
                message = client.bind(**bind_options).invoke(messages)
                usage = _usage_from_message(message)
                attempt_usage = usage if _message_reports_usage(message) else None
                if attempt_usage is not None:
                    usage_source = "provider_response"
                total_usage = TokenUsage(
                    input_tokens=total_usage.input_tokens + usage.input_tokens,
                    output_tokens=total_usage.output_tokens + usage.output_tokens,
                )
                raw_text = _content_text(getattr(message, "content", ""))
                previous_invalid_output = raw_text
                value = output_schema.model_validate(_json_object(raw_text))
                if result_validator is not None:
                    result_validator(value)
                response_meta = getattr(message, "response_metadata", None) or {}
                finish_reason = str(response_meta.get("finish_reason", ""))
                self._record_attempt(
                    call_id=call_id, stage=stage, prompt=prompt, config_sha256=config_sha256,
                    rate_id=rate_id, attempt=attempt, status="ok", usage=attempt_usage,
                    usage_source=usage_source,
                    duration_seconds=perf_counter() - attempt_started,
                    finish_reason=finish_reason,
                )
                response_id = str(getattr(message, "id", "") or "")
                cost = (
                    total_usage.input_tokens
                    * self.settings.input_cost_per_million
                    + total_usage.output_tokens
                    * self.settings.output_cost_per_million
                ) / 1_000_000
                return ProviderCallResult(
                    value=value,
                    usage=total_usage,
                    estimated_cost=cost,
                    metadata=AgentCallMetadata(
                        provider=self.settings.provider,
                        model_name=self.settings.model_name,
                        prompt_id=prompt.prompt_id,
                        prompt_version=prompt.version,
                        prompt_sha256=prompt.sha256,
                        response_id=response_id,
                        finish_reason=finish_reason,
                        attempts=attempt,
                        thinking_mode=self.settings.thinking_mode,
                    ),
                )
            except (KeyboardInterrupt, asyncio.CancelledError):
                self._record_attempt(
                    call_id=call_id, stage=stage, prompt=prompt,
                    config_sha256=config_sha256, rate_id=rate_id,
                    attempt=attempt, status="cancelled", usage=attempt_usage,
                    usage_source=usage_source,
                    duration_seconds=perf_counter() - attempt_started,
                    error_type="Cancelled",
                )
                raise
            except Exception as exc:
                if isinstance(exc, CallLedgerWriteError):
                    cost = (
                        total_usage.input_tokens * self.settings.input_cost_per_million
                        + total_usage.output_tokens * self.settings.output_cost_per_million
                    ) / 1_000_000
                    raise ProviderInvocationError(
                        f"{stage} stopped because model call accounting could not be persisted",
                        attempts=attempts_made,
                        usage=total_usage,
                        estimated_cost=cost,
                    ) from exc
                raw_error = f"{type(exc).__name__}: {exc}"
                api_key = os.getenv(self.settings.api_key_env, "").strip()
                last_error = raw_error.replace(api_key, "[REDACTED]") if api_key else raw_error
                # LangChain may raise before returning a message when the
                # provider reports a truncated completion. Its exception text
                # can still carry the provider's actual usage; count it once.
                if "length limit was reached" in raw_error.lower():
                    prompt_match = re.search(r"prompt_tokens=(\d+)", raw_error)
                    output_match = re.search(r"completion_tokens=(\d+)", raw_error)
                    if prompt_match and output_match and attempt_usage is None:
                        attempt_usage = TokenUsage(
                            input_tokens=int(prompt_match.group(1)),
                            output_tokens=int(output_match.group(1)),
                        )
                        total_usage = TokenUsage(
                            input_tokens=total_usage.input_tokens + attempt_usage.input_tokens,
                            output_tokens=total_usage.output_tokens + attempt_usage.output_tokens,
                        )
                        usage_source = "truncation_exception"
                self._record_attempt(
                    call_id=call_id, stage=stage, prompt=prompt, config_sha256=config_sha256,
                    rate_id=rate_id, attempt=attempt,
                    status=(
                        "truncated" if "length limit was reached" in raw_error.lower()
                        else "invalid_output" if attempt_usage is not None else "failed"
                    ),
                    usage=attempt_usage,
                    usage_source=usage_source,
                    duration_seconds=perf_counter() - attempt_started,
                    error_type=type(exc).__name__,
                )
                # A whole-document import that already hit the output cap will
                # hit it again with the same schema. Retrying adds the failed
                # response to the prompt and only increases cost/context use.
                if _is_non_retryable_error(exc) or (
                    type(exc).__name__ == "LengthFinishReasonError"
                    or "length limit was reached" in raw_error.lower()
                ):
                    break
                correction = (
                    "上一次 JSON 未通过程序校验。请保留其中正确内容，只修复下述"
                    "契约错误，然后重新输出完整 JSON；不要解释，不要改动无关字段。\n"
                    f"校验错误：{last_error[:2000]}"
                )
        cost = (
            total_usage.input_tokens * self.settings.input_cost_per_million
            + total_usage.output_tokens * self.settings.output_cost_per_million
        ) / 1_000_000
        raise ProviderInvocationError(
            f"{stage} failed after {attempts_made} real model "
            f"attempts; last error: {last_error}",
            attempts=attempts_made,
            usage=total_usage,
            estimated_cost=cost,
        )

    def _record_attempt(
        self, *, call_id: str, stage: str, prompt: PromptSpec, config_sha256: str,
        rate_id: str, attempt: int, status: str, usage: TokenUsage | None,
        usage_source: str, duration_seconds: float, finish_reason: str = "", error_type: str = "",
    ) -> None:
        ledger = current_ledger()
        if ledger is None:
            return
        cost = None if usage is None else (
            usage.input_tokens * self.settings.input_cost_per_million
            + usage.output_tokens * self.settings.output_cost_per_million
        ) / 1_000_000
        try:
            ledger.append(ModelCallAttempt(
                call_id=call_id,
                attempt_id=uuid4().hex,
                stage=stage,
                model_name=self.settings.model_name,
                prompt_id=prompt.prompt_id,
                prompt_sha256=prompt.sha256,
                config_sha256=config_sha256,
                rate_id=rate_id,
                attempt_index=attempt,
                status=status,
                usage_source=usage_source,
                input_tokens=usage.input_tokens if usage is not None else None,
                output_tokens=usage.output_tokens if usage is not None else None,
                estimated_cost=cost,
                duration_seconds=max(0.0, duration_seconds),
                finish_reason=finish_reason,
                error_type=error_type,
            ))
        except OSError as exc:
            raise CallLedgerWriteError("model call accounting write failed") from exc
