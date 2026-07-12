from __future__ import annotations

import json
from typing import Any, Sequence

from .base import (
    LLMProvider,
    ModelMessage,
    ModelResponse,
    ProviderConfig,
    ProviderConfigurationError,
    ProviderError,
    ProviderResponseError,
    ToolCall,
    ToolDefinition,
)


class OpenAIChatCompletionsProvider(LLMProvider):
    """OpenAI-compatible Chat Completions provider.

    This protocol is implemented by DeepSeek and many local or hosted model
    services that do not implement the newer Responses API.
    """

    def __init__(self, config: ProviderConfig, *, client: Any | None = None) -> None:
        self.config = config
        self._client = client if client is not None else self._build_client(config)

    @staticmethod
    def _build_client(config: ProviderConfig) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - exercised without dependency
            raise ProviderConfigurationError(
                "the 'openai' package is required for OpenAIChatCompletionsProvider"
            ) from exc

        client = OpenAI(
            api_key=config.api_key or "not-required",
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )
        chat = getattr(client, "chat", None)
        if chat is None or not hasattr(chat, "completions"):
            raise ProviderConfigurationError(
                "the installed 'openai' package does not support Chat Completions"
            )
        return client

    def complete(
        self,
        messages: Sequence[ModelMessage],
        tools: Sequence[ToolDefinition] = (),
    ) -> ModelResponse:
        request: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": [_message_payload(message) for message in messages],
        }
        if tools:
            request["tools"] = [_tool_payload(tool) for tool in tools]
        if self.config.temperature is not None:
            request["temperature"] = self.config.temperature
        if self.config.max_tokens is not None:
            request["max_tokens"] = self.config.max_tokens

        try:
            response = self._client.chat.completions.create(**request)
        except Exception as exc:
            raise ProviderError(
                "OpenAI-compatible Chat Completions request failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        return _normalize_response(response, self.config.model_name)


def _message_payload(message: ModelMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.role == "assistant" and message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(
                        call.arguments, ensure_ascii=False, sort_keys=True
                    ),
                },
            }
            for call in message.tool_calls
        ]
    if message.role == "tool":
        payload["tool_call_id"] = message.tool_call_id
    return payload


def _tool_payload(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _normalize_response(response: Any, configured_model: str) -> ModelResponse:
    choices = _value(response, "choices", ()) or ()
    if not choices:
        raise ProviderResponseError("Chat Completions response has no choices")
    message = _value(choices[0], "message")
    if message is None:
        raise ProviderResponseError("Chat Completions response has no message")

    tool_calls: list[ToolCall] = []
    for item in _value(message, "tool_calls", ()) or ():
        function = _value(item, "function")
        raw_arguments = _value(function, "arguments", "{}")
        try:
            arguments = (
                json.loads(raw_arguments)
                if isinstance(raw_arguments, str)
                else raw_arguments
            )
        except json.JSONDecodeError as exc:
            raise ProviderResponseError(
                f"tool arguments are not valid JSON: {exc.msg}"
            ) from exc
        if not isinstance(arguments, dict):
            raise ProviderResponseError("tool arguments must decode to a JSON object")
        tool_calls.append(
            ToolCall(
                call_id=str(_value(item, "id", "")),
                name=str(_value(function, "name", "")),
                arguments=dict(arguments),
            )
        )

    usage = _value(response, "usage")
    input_tokens = _optional_int(_value(usage, "prompt_tokens"))
    output_tokens = _optional_int(_value(usage, "completion_tokens"))
    total_tokens = _optional_int(_value(usage, "total_tokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    return ModelResponse(
        content=_content_text(_value(message, "content")),
        tool_calls=tuple(tool_calls),
        model_name=_optional_text(_value(response, "model")) or configured_model,
        response_id=_optional_text(_value(response, "id")),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost=_optional_float(_value(response, "cost")),
    )


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            text = _value(part, "text")
            if text:
                parts.append(str(text))
        return "".join(parts)
    raise ProviderResponseError("assistant content is not text")


def _value(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
