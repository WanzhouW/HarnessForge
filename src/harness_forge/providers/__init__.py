"""Model-provider abstractions and concrete API integrations."""

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
from .openai_compatible import OpenAICompatibleProvider
from .openai_chat_completions import OpenAIChatCompletionsProvider


def create_provider(config: ProviderConfig) -> LLMProvider:
    """Create the concrete provider selected by ``config.provider_api``."""

    if config.provider_api == "responses":
        return OpenAICompatibleProvider(config)
    if config.provider_api == "chat_completions":
        return OpenAIChatCompletionsProvider(config)
    raise ProviderConfigurationError(
        f"unsupported provider_api: {config.provider_api}"
    )

__all__ = [
    "LLMProvider",
    "ModelMessage",
    "ModelResponse",
    "OpenAICompatibleProvider",
    "OpenAIChatCompletionsProvider",
    "ProviderConfig",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderResponseError",
    "ToolCall",
    "ToolDefinition",
    "create_provider",
]
