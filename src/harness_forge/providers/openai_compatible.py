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


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI Responses API provider with configurable compatible base URL.

    Despite the historical class name, this provider requires the specific
    ``/responses`` protocol. Use ``OpenAIChatCompletionsProvider`` for services
    such as DeepSeek that implement only ``/chat/completions``.
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
                "the 'openai' package is required for OpenAICompatibleProvider"
            ) from exc

        client = OpenAI(
            api_key=config.api_key or "not-required",
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )
        if not hasattr(client, "responses"):
            raise ProviderConfigurationError(
                "the installed 'openai' package does not support the Responses API"
            )
        return client

    def complete(
        self,
        messages: Sequence[ModelMessage],
        tools: Sequence[ToolDefinition] = (),
    ) -> ModelResponse:
        instructions, input_items = _build_input(messages)
        request: dict[str, Any] = {
            "model": self.config.model_name,
            "input": input_items,
            "store": False,
            "parallel_tool_calls": False,
        }
        if instructions:
            request["instructions"] = instructions
        if tools:
            request["tools"] = [_tool_payload(tool) for tool in tools]
        if self.config.temperature is not None:
            request["temperature"] = self.config.temperature
        if self.config.max_tokens is not None:
            request["max_output_tokens"] = self.config.max_tokens

        try:
            response = self._client.responses.create(**request)
        except Exception as exc:
            raise ProviderError(
                f"OpenAI-compatible Responses request failed: {type(exc).__name__}: {exc}"
            ) from exc
        return _normalize_response(response, self.config.model_name)


def _tool_payload(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
    }


def _build_input(messages: Sequence[ModelMessage]) -> tuple[str, list[dict[str, Any]]]:
    instructions: list[str] = []
    items: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "system":
            if message.content:
                instructions.append(message.content)
            continue
        if message.role in {"user", "assistant"} and message.content:
            items.append({"role": message.role, "content": message.content})
        if message.role == "assistant":
            for call in message.tool_calls:
                item: dict[str, Any] = {
                    "type": "function_call",
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": json.dumps(
                        call.arguments, ensure_ascii=False, sort_keys=True
                    ),
                }
                if call.response_item_id:
                    item["id"] = call.response_item_id
                items.append(item)
        elif message.role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": message.content,
                }
            )
    return "\n\n".join(instructions), items


def _normalize_response(response: Any, configured_model: str) -> ModelResponse:
    tool_calls: list[ToolCall] = []
    for item in _value(response, "output", ()) or ():
        if _value(item, "type") != "function_call":
            continue
        raw_arguments = _value(item, "arguments", "{}")
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
        except json.JSONDecodeError as exc:
            raise ProviderResponseError(
                f"tool arguments are not valid JSON: {exc.msg}"
            ) from exc
        if not isinstance(arguments, dict):
            raise ProviderResponseError("tool arguments must decode to a JSON object")
        tool_calls.append(
            ToolCall(
                call_id=str(_value(item, "call_id", "")),
                name=str(_value(item, "name", "")),
                arguments=dict(arguments),
                response_item_id=_optional_text(_value(item, "id")),
            )
        )

    usage = _value(response, "usage")
    input_tokens = _optional_int(_value(usage, "input_tokens"))
    output_tokens = _optional_int(_value(usage, "output_tokens"))
    total_tokens = _optional_int(_value(usage, "total_tokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    content = _value(response, "output_text", "") or _extract_output_text(response)
    return ModelResponse(
        content=str(content or ""),
        tool_calls=tuple(tool_calls),
        model_name=_optional_text(_value(response, "model")) or configured_model,
        response_id=_optional_text(_value(response, "id")),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost=_optional_float(_value(response, "cost")),
    )


def _extract_output_text(response: Any) -> str:
    parts: list[str] = []
    for item in _value(response, "output", ()) or ():
        if _value(item, "type") != "message":
            continue
        for content in _value(item, "content", ()) or ():
            if _value(content, "type") in {"output_text", "text"}:
                text = _value(content, "text")
                if text:
                    parts.append(str(text))
    return "".join(parts)


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
