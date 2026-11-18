"""The only module that imports the Anthropic SDK. Everything else sees `ClaudeClient`."""

import logging
from typing import Any

import anthropic

from app.services.orchestrator import ClaudeMessage, ClaudeUnavailable
from app.settings import Settings

logger = logging.getLogger("launchwise.explain")

REQUEST_TIMEOUT_SECONDS = 30.0
SDK_RETRIES = 1  # connection errors and 429/5xx; invalid *content* is retried by the orchestrator


class AnthropicClaudeClient:
    """Sends one Messages request and returns the reply text, or raises `ClaudeUnavailable`.

    Sampling parameters are left out on purpose: current models reject them.
    """

    def __init__(self, client: Any, *, model: str) -> None:
        self._client = client
        self._model = model

    def complete(self, *, system: str, messages: list[ClaudeMessage], max_tokens: int) -> str:
        try:
            response = self._client.messages.create(
                model=self._model, max_tokens=max_tokens, system=system, messages=messages
            )
        except anthropic.APIError as exc:
            # The type only: the SDK's message can carry request details.
            logger.warning("claude request failed: %s", type(exc).__name__)
            raise ClaudeUnavailable("the Claude request failed") from exc
        if response.stop_reason in ("refusal", "max_tokens"):
            raise ClaudeUnavailable(f"stopped early: {response.stop_reason}")
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if not text:
            raise ClaudeUnavailable("empty reply")
        return text


def claude_client_from_settings(settings: Settings) -> AnthropicClaudeClient | None:
    """None unless a real key and model are set, so a missing key just means the template."""
    if not settings.claude_enabled or settings.anthropic_api_key is None:
        return None
    sdk = anthropic.Anthropic(
        api_key=settings.anthropic_api_key.get_secret_value().strip(),
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=SDK_RETRIES,
    )
    return AnthropicClaudeClient(sdk, model=(settings.claude_model or "").strip())
