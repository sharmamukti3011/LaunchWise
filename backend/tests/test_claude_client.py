"""The Anthropic adapter: settings in, text out, every failure mapped to ClaudeUnavailable."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from app.services.claude_client import AnthropicClaudeClient, claude_client_from_settings
from app.services.orchestrator import ClaudeMessage, ClaudeUnavailable
from app.settings import Settings


def block(text: str) -> Any:
    return SimpleNamespace(type="text", text=text)


class FakeMessages:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result, self.error = result, error
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.result


def sdk(result: Any = None, error: Exception | None = None) -> tuple[Any, FakeMessages]:
    messages = FakeMessages(result, error)
    return SimpleNamespace(messages=messages), messages


def message(*blocks: Any, stop_reason: str = "end_turn") -> Any:
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


MESSAGES: list[ClaudeMessage] = [{"role": "user", "content": "hi"}]


def test_the_request_uses_the_model_it_was_given_and_returns_the_text() -> None:
    client, messages = sdk(message(block('{"summary": "x"}')))
    adapter = AnthropicClaudeClient(client, model="model-from-env")
    assert adapter.complete(system="sys", messages=MESSAGES, max_tokens=500) == '{"summary": "x"}'
    assert messages.kwargs["model"] == "model-from-env"
    assert messages.kwargs["system"] == "sys" and messages.kwargs["max_tokens"] == 500
    assert messages.kwargs["messages"] == MESSAGES
    assert "temperature" not in messages.kwargs  # removed on current models


def test_non_text_blocks_such_as_thinking_are_skipped_and_text_is_joined() -> None:
    thinking = SimpleNamespace(type="thinking", thinking="...")
    client, _ = sdk(message(thinking, block("a"), block("b")))
    assert (
        AnthropicClaudeClient(client, model="m").complete(
            system="s", messages=MESSAGES, max_tokens=10
        )
        == "ab"
    )


@pytest.mark.parametrize(
    "result",
    [message(), message(block("   ")), message(block("x"), stop_reason="refusal"),
     message(block("x"), stop_reason="max_tokens")],
)  # fmt: skip
def test_empty_refused_or_truncated_replies_are_unavailable(result: Any) -> None:
    client, _ = sdk(result)
    with pytest.raises(ClaudeUnavailable):
        AnthropicClaudeClient(client, model="m").complete(
            system="s", messages=MESSAGES, max_tokens=10
        )


def test_sdk_errors_become_unavailable_without_leaking_their_text() -> None:
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x.invalid"))
    client, _ = sdk(error=error)
    with pytest.raises(ClaudeUnavailable) as caught:
        AnthropicClaudeClient(client, model="m").complete(
            system="s", messages=MESSAGES, max_tokens=10
        )
    assert "x.invalid" not in str(caught.value)


# ---- building it from settings ----------------------------------------------------------------


def settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, app_env="test", **overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"anthropic_api_key": "sk-ant-x"},  # no model
        {"claude_model": "some-model"},  # no key
        {"anthropic_api_key": "your-key-here", "claude_model": "some-model"},  # .env.example
        {"anthropic_api_key": "sk-ant-x", "claude_model": "your-model-name-here"},
        {"anthropic_api_key": "  ", "claude_model": "some-model"},
    ],
)
def test_without_a_real_key_and_model_there_is_no_client(overrides: dict[str, Any]) -> None:
    cfg = settings(**overrides)
    assert cfg.claude_enabled is False
    assert claude_client_from_settings(cfg) is None


def test_with_a_key_and_a_model_a_client_is_built_and_the_key_stays_secret() -> None:
    cfg = settings(anthropic_api_key="sk-ant-secret", claude_model="some-model")
    assert cfg.claude_enabled is True
    assert isinstance(claude_client_from_settings(cfg), AnthropicClaudeClient)
    assert "sk-ant-secret" not in repr(cfg)
