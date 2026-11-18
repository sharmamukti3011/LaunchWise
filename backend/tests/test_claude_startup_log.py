"""The startup line that says whether Claude explain is on, and why not. Never a key or a model."""

import logging
from typing import Any

import pytest

from app.main import create_app
from app.services.claude_client import claude_startup_message
from app.settings import Settings
from tests.fakes import FakeClaude

SECRET_KEY = "sk-ant-api03-SECRETVALUE"
SECRET_MODEL = "secret-model-name-123"


def settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, app_env="test", **overrides)


@pytest.mark.parametrize(
    ("overrides", "status", "needle"),
    [
        ({}, "missing_key", "ANTHROPIC_API_KEY is not set"),
        ({"anthropic_api_key": "  "}, "missing_key", "ANTHROPIC_API_KEY is not set"),
        ({"anthropic_api_key": "your-key-here", "claude_model": "m"}, "placeholder_key",
         "still the .env.example placeholder"),
        ({"anthropic_api_key": SECRET_KEY}, "missing_model", "CLAUDE_MODEL is not set"),
        ({"anthropic_api_key": SECRET_KEY, "claude_model": "your-model-name-here"},
         "placeholder_model", "CLAUDE_MODEL is still the .env.example placeholder"),
        ({"anthropic_api_key": SECRET_KEY, "claude_model": SECRET_MODEL}, "enabled", "enabled"),
    ],
)  # fmt: skip
def test_each_state_has_a_status_and_a_plain_message(
    overrides: dict[str, Any], status: str, needle: str
) -> None:
    cfg = settings(**overrides)
    assert cfg.claude_status == status
    assert cfg.claude_enabled == (status == "enabled")
    message = claude_startup_message(cfg, injected=False)
    assert needle in message
    assert message.startswith("Claude explain: ")


def test_the_enabled_message_states_the_caps_and_the_disabled_one_names_the_fallback() -> None:
    on = claude_startup_message(
        settings(
            anthropic_api_key=SECRET_KEY,
            claude_model=SECRET_MODEL,
            claude_max_calls_per_session=7,
            claude_max_calls_global=99,
        ),
        injected=False,
    )
    assert "7 calls per visitor" in on and "99 calls in total" in on
    off = claude_startup_message(settings(), injected=False)
    assert "template" in off


def test_no_message_ever_contains_the_key_or_the_model_name() -> None:
    for overrides in (
        {"anthropic_api_key": SECRET_KEY},
        {"anthropic_api_key": SECRET_KEY, "claude_model": SECRET_MODEL},
        {"claude_model": SECRET_MODEL},
    ):
        message = claude_startup_message(settings(**overrides), injected=False)
        assert SECRET_KEY not in message and SECRET_MODEL not in message


def test_an_injected_client_is_reported_as_such() -> None:
    assert "injected" in claude_startup_message(settings(), injected=True)


def test_create_app_logs_the_line_once_at_info(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="launchwise.explain"):
        create_app(settings(anthropic_api_key=SECRET_KEY, claude_model=SECRET_MODEL))
    lines = [r for r in caplog.records if r.getMessage().startswith("Claude explain: ")]
    assert len(lines) == 1 and lines[0].levelno == logging.INFO
    text = lines[0].getMessage()
    assert SECRET_KEY not in text and SECRET_MODEL not in text and "enabled" in text


def test_a_disabled_app_logs_a_warning_with_the_reason(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="launchwise.explain"):
        create_app(settings())
    [record] = [r for r in caplog.records if r.getMessage().startswith("Claude explain: ")]
    assert record.levelno == logging.WARNING
    assert "ANTHROPIC_API_KEY is not set" in record.getMessage()


def test_an_injected_fake_logs_enabled_without_needing_settings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="launchwise.explain"):
        create_app(settings(), claude=FakeClaude())
    [record] = [r for r in caplog.records if r.getMessage().startswith("Claude explain: ")]
    assert record.levelno == logging.INFO and "injected" in record.getMessage()
