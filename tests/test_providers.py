from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from harness_forge.providers import (
    ModelMessage,
    OpenAIChatCompletionsProvider,
    OpenAICompatibleProvider,
    ProviderConfig,
    ProviderConfigurationError,
    ToolCall,
    ToolDefinition,
    create_provider,
)


class _FakeResponsesResource:
    def __init__(self, response: object) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    def create(self, **request: object) -> object:
        self.requests.append(request)
        return self.response


class _FakeOpenAIClient:
    def __init__(self, response: object) -> None:
        self.responses = _FakeResponsesResource(response)


class ProviderConfigTests(unittest.TestCase):
    def test_loads_settings_from_dotenv_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                "OPENAI_API_KEY=dotenv-key\n"
                "OPENAI_BASE_URL=https://dotenv.example/v1/\n"
                "MODEL_NAME=dotenv-model\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config = ProviderConfig.from_env(dotenv_path=dotenv_path)

        self.assertEqual(config.api_key, "dotenv-key")
        self.assertEqual(config.base_url, "https://dotenv.example/v1")
        self.assertEqual(config.model_name, "dotenv-model")

    def test_process_environment_takes_precedence_over_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text("MODEL_NAME=dotenv-model\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"MODEL_NAME": "process-model"},
                clear=True,
            ):
                config = ProviderConfig.from_env(dotenv_path=dotenv_path)

        self.assertEqual(config.model_name, "process-model")

    def test_loads_openai_compatible_settings_from_environment(self) -> None:
        with patch("harness_forge.providers.base.load_dotenv") as loader:
            config = ProviderConfig.from_env(
                env={
                    "OPENAI_API_KEY": "secret-test-key",
                    "OPENAI_BASE_URL": "https://example.test/v1/",
                    "MODEL_NAME": "test-model",
                },
                temperature=0.25,
                max_tokens=512,
                timeout_seconds=15,
                max_retries=3,
            )

        loader.assert_not_called()
        self.assertEqual(config.model_name, "test-model")
        self.assertEqual(config.base_url, "https://example.test/v1")
        self.assertEqual(config.api_key, "secret-test-key")
        self.assertEqual(config.temperature, 0.25)
        self.assertEqual(config.max_tokens, 512)
        self.assertEqual(config.timeout_seconds, 15)
        self.assertEqual(config.max_retries, 3)
        self.assertNotIn("secret-test-key", str(config.public_dict()))

    def test_loads_and_normalizes_provider_api(self) -> None:
        config = ProviderConfig.from_env(
            env={
                "MODEL_NAME": "deepseek-chat",
                "PROVIDER_API": "chat-completions",
            }
        )

        self.assertEqual(config.provider_api, "chat_completions")
        self.assertEqual(config.public_dict()["provider_api"], "chat_completions")

    def test_rejects_unknown_provider_api(self) -> None:
        with self.assertRaisesRegex(
            ProviderConfigurationError, "provider_api must be"
        ):
            ProviderConfig(model_name="test-model", provider_api="messages")

    def test_provider_api_does_not_break_existing_positional_arguments(self) -> None:
        config = ProviderConfig(
            "test-model", "test-key", "https://example.test/v1"
        )

        self.assertEqual(config.api_key, "test-key")
        self.assertEqual(config.base_url, "https://example.test/v1")
        self.assertEqual(config.provider_api, "responses")

    def test_rejects_missing_model_name(self) -> None:
        with self.assertRaises(ProviderConfigurationError):
            ProviderConfig.from_env(env={})


class OpenAICompatibleProviderTests(unittest.TestCase):
    def test_builds_official_sdk_client_with_timeout_and_retries(self) -> None:
        config = ProviderConfig(
            model_name="test-model",
            api_key="test-key",
            base_url="https://example.test/v1",
            timeout_seconds=17,
            max_retries=4,
        )
        fake_client = SimpleNamespace(responses=SimpleNamespace())

        with patch("openai.OpenAI", return_value=fake_client) as client_type:
            provider = OpenAICompatibleProvider(config)

        self.assertIs(provider._client, fake_client)
        client_type.assert_called_once_with(
            api_key="test-key",
            base_url="https://example.test/v1",
            timeout=17,
            max_retries=4,
        )

    def test_normalizes_responses_api_tool_call_and_usage(self) -> None:
        raw_response = SimpleNamespace(
            id="resp_test",
            model="served-model",
            output_text="",
            output=[
                SimpleNamespace(
                    type="function_call",
                    id="fc_test",
                    call_id="call_test",
                    name="read_file",
                    arguments='{"path":"README.md"}',
                )
            ],
            usage=SimpleNamespace(
                input_tokens=21,
                output_tokens=4,
                total_tokens=25,
            ),
        )
        client = _FakeOpenAIClient(raw_response)
        config = ProviderConfig(
            model_name="requested-model",
            api_key="test-key",
            base_url="https://example.test/v1",
            temperature=0.1,
            max_tokens=256,
        )
        provider = OpenAICompatibleProvider(config, client=client)

        response = provider.complete(
            [
                ModelMessage(role="system", content="System prompt"),
                ModelMessage(role="user", content="Read the README"),
            ],
            [
                ToolDefinition(
                    name="read_file",
                    description="Read a file.",
                    parameters={
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                )
            ],
        )

        self.assertEqual(response.model_name, "served-model")
        self.assertEqual(response.response_id, "resp_test")
        self.assertEqual(response.input_tokens, 21)
        self.assertEqual(response.output_tokens, 4)
        self.assertEqual(response.total_tokens, 25)
        self.assertEqual(len(response.tool_calls), 1)
        self.assertEqual(response.tool_calls[0].name, "read_file")
        self.assertEqual(response.tool_calls[0].arguments, {"path": "README.md"})

        request = client.responses.requests[0]
        self.assertEqual(request["model"], "requested-model")
        self.assertEqual(request["instructions"], "System prompt")
        self.assertEqual(request["temperature"], 0.1)
        self.assertEqual(request["max_output_tokens"], 256)
        self.assertFalse(request["store"])
        self.assertFalse(request["parallel_tool_calls"])
        self.assertEqual(request["tools"][0]["name"], "read_file")


class _FakeChatCompletionsResource:
    def __init__(self, response: object) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    def create(self, **request: object) -> object:
        self.requests.append(request)
        return self.response


class _FakeChatClient:
    def __init__(self, response: object) -> None:
        self.chat = SimpleNamespace(
            completions=_FakeChatCompletionsResource(response)
        )


class OpenAIChatCompletionsProviderTests(unittest.TestCase):
    def test_builds_official_sdk_client_with_timeout_and_retries(self) -> None:
        config = ProviderConfig(
            model_name="deepseek-chat",
            provider_api="chat_completions",
            api_key="test-key",
            base_url="https://api.deepseek.com",
            timeout_seconds=19,
            max_retries=1,
        )
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace())
        )

        with patch("openai.OpenAI", return_value=fake_client) as client_type:
            provider = OpenAIChatCompletionsProvider(config)

        self.assertIs(provider._client, fake_client)
        client_type.assert_called_once_with(
            api_key="test-key",
            base_url="https://api.deepseek.com",
            timeout=19,
            max_retries=1,
        )

    def test_normalizes_tool_call_usage_and_chat_request(self) -> None:
        raw_response = SimpleNamespace(
            id="chatcmpl_test",
            model="deepseek-served-model",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="",
                        tool_calls=[
                            SimpleNamespace(
                                id="call_next",
                                function=SimpleNamespace(
                                    name="read_file",
                                    arguments='{"path":"next.py"}',
                                ),
                            )
                        ],
                    )
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=31,
                completion_tokens=7,
                total_tokens=38,
            ),
        )
        client = _FakeChatClient(raw_response)
        config = ProviderConfig(
            model_name="deepseek-chat",
            provider_api="chat_completions",
            api_key="test-key",
            base_url="https://api.deepseek.com",
            temperature=0.2,
            max_tokens=300,
        )
        provider = OpenAIChatCompletionsProvider(config, client=client)

        response = provider.complete(
            [
                ModelMessage(role="system", content="System prompt"),
                ModelMessage(role="user", content="Inspect files"),
                ModelMessage(
                    role="assistant",
                    tool_calls=(
                        ToolCall(
                            call_id="call_previous",
                            name="list_dir",
                            arguments={"path": "."},
                        ),
                    ),
                ),
                ModelMessage(
                    role="tool",
                    content='{"success":true}',
                    tool_call_id="call_previous",
                ),
            ],
            [
                ToolDefinition(
                    name="read_file",
                    description="Read a file.",
                    parameters={
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                )
            ],
        )

        self.assertEqual(response.model_name, "deepseek-served-model")
        self.assertEqual(response.response_id, "chatcmpl_test")
        self.assertEqual(response.input_tokens, 31)
        self.assertEqual(response.output_tokens, 7)
        self.assertEqual(response.total_tokens, 38)
        self.assertEqual(response.tool_calls[0].call_id, "call_next")
        self.assertEqual(response.tool_calls[0].arguments, {"path": "next.py"})

        request = client.chat.completions.requests[0]
        self.assertEqual(request["model"], "deepseek-chat")
        self.assertEqual(request["temperature"], 0.2)
        self.assertEqual(request["max_tokens"], 300)
        self.assertEqual(request["messages"][0]["role"], "system")
        self.assertEqual(
            request["messages"][2]["tool_calls"][0]["function"]["name"],
            "list_dir",
        )
        self.assertEqual(
            request["messages"][3]["tool_call_id"], "call_previous"
        )
        self.assertEqual(
            request["tools"][0]["function"]["name"], "read_file"
        )

    def test_factory_selects_chat_completions_provider(self) -> None:
        config = ProviderConfig(
            model_name="deepseek-chat",
            provider_api="chat_completions",
        )
        sentinel = object()
        with patch(
            "harness_forge.providers.OpenAIChatCompletionsProvider",
            return_value=sentinel,
        ) as provider_type:
            provider = create_provider(config)

        self.assertIs(provider, sentinel)
        provider_type.assert_called_once_with(config)


if __name__ == "__main__":
    unittest.main()
