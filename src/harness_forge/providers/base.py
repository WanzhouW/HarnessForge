from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from dotenv import load_dotenv


class ProviderError(RuntimeError):
    """Base error raised at the model-provider boundary."""


class ProviderConfigurationError(ProviderError, ValueError):
    """Raised when provider configuration is invalid or incomplete."""


class ProviderResponseError(ProviderError):
    """Raised when an API response cannot be normalized safely."""


@dataclass(frozen=True)
class ProviderConfig:
    """Configuration shared by LLM providers.

    Explicit values take precedence over environment values. API keys are
    optional so OpenAI-compatible local endpoints can run without credentials;
    the official OpenAI endpoint still requires ``OPENAI_API_KEY``.
    """

    model_name: str
    api_key: str | None = None
    base_url: str = "https://api.openai.com/v1"
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float = 60.0
    max_retries: int = 2
    provider_api: str = "responses"

    def __post_init__(self) -> None:
        model_name = self.model_name.strip()
        provider_api = self.provider_api.strip().lower().replace("-", "_")
        provider_api = {
            "chat": "chat_completions",
            "chat_completion": "chat_completions",
        }.get(provider_api, provider_api)
        base_url = self.base_url.strip().rstrip("/")
        api_key = self.api_key.strip() if self.api_key else None
        if not model_name:
            raise ProviderConfigurationError("model_name must be non-empty")
        if provider_api not in {"responses", "chat_completions"}:
            raise ProviderConfigurationError(
                "provider_api must be 'responses' or 'chat_completions'"
            )
        if not base_url:
            raise ProviderConfigurationError("base_url must be non-empty")
        if self.temperature is not None and self.temperature < 0:
            raise ProviderConfigurationError("temperature must be non-negative")
        if self.max_tokens is not None and self.max_tokens < 1:
            raise ProviderConfigurationError("max_tokens must be positive")
        if self.timeout_seconds <= 0:
            raise ProviderConfigurationError("timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ProviderConfigurationError("max_retries must be non-negative")
        object.__setattr__(self, "model_name", model_name)
        object.__setattr__(self, "provider_api", provider_api)
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "api_key", api_key)

    @classmethod
    def from_env(
        cls,
        *,
        env: Mapping[str, str] | None = None,
        dotenv_path: str | Path | None = None,
        model_name: str | None = None,
        provider_api: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
    ) -> "ProviderConfig":
        if env is None:
            load_dotenv(dotenv_path=dotenv_path or Path.cwd() / ".env")
            values: Mapping[str, str] = os.environ
        else:
            values = env
        resolved_model = model_name or values.get("MODEL_NAME", "")
        resolved_provider_api = provider_api or values.get("PROVIDER_API", "responses")
        resolved_key = api_key if api_key is not None else values.get("OPENAI_API_KEY")
        resolved_url = base_url or values.get(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
        return cls(
            model_name=resolved_model,
            provider_api=resolved_provider_api,
            api_key=resolved_key,
            base_url=resolved_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    def public_dict(self) -> dict[str, Any]:
        """Return configuration safe to place in results or logs."""

        return {
            "model_name": self.model_name,
            "provider_api": self.provider_api,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "api_key_configured": self.api_key is not None,
        }


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    response_item_id: str | None = None

    def __post_init__(self) -> None:
        if not self.call_id.strip():
            raise ProviderResponseError("tool call_id must be non-empty")
        if not self.name.strip():
            raise ProviderResponseError("tool name must be non-empty")


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ModelMessage:
    role: str
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise ValueError(f"unsupported model-message role: {self.role}")
        if self.role == "tool" and not self.tool_call_id:
            raise ValueError("tool messages require tool_call_id")
        if self.role != "tool" and self.tool_call_id is not None:
            raise ValueError("tool_call_id is only valid for tool messages")
        if self.role != "assistant" and self.tool_calls:
            raise ValueError("tool_calls are only valid for assistant messages")


@dataclass(frozen=True)
class ModelResponse:
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    model_name: str | None = None
    response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None


class LLMProvider(ABC):
    """Provider-neutral synchronous model interface used by the agent loop."""

    config: ProviderConfig

    @abstractmethod
    def complete(
        self,
        messages: Sequence[ModelMessage],
        tools: Sequence[ToolDefinition] = (),
    ) -> ModelResponse:
        """Return model text, one or more requested tool calls, and usage."""
