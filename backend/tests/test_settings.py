"""Settings defaults and the .env.example that documents them."""

import re
from pathlib import Path

import pytest

from app.settings import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def _example_keys() -> set[str]:
    keys = set()
    for line in ENV_EXAMPLE.read_text().splitlines():
        match = re.match(r"^([A-Z][A-Z0-9_]*)=", line)
        if match:
            keys.add(match.group(1))
    return keys


def test_contact_form_is_disabled_by_default() -> None:
    assert Settings(_env_file=None).contact_enabled is False


@pytest.mark.parametrize(("raw", "expected"), [("true", True), ("false", False), ("1", True)])
def test_contact_enabled_reads_the_environment(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
) -> None:
    monkeypatch.setenv("CONTACT_ENABLED", raw)
    assert Settings(_env_file=None).contact_enabled is expected


def test_env_example_documents_every_setting() -> None:
    missing = {name.upper() for name in Settings.model_fields} - _example_keys()
    assert not missing, f".env.example is missing: {sorted(missing)}"


def test_env_example_ships_contact_disabled_and_the_site_domain() -> None:
    text = ENV_EXAMPLE.read_text()
    assert re.search(r"^CONTACT_ENABLED=false\s*$", text, re.MULTILINE)
    assert "SITE_DOMAIN" in _example_keys()


def test_env_example_contains_placeholders_not_real_secrets() -> None:
    values = {
        key: value
        for key, value in (
            line.split("=", 1) for line in ENV_EXAMPLE.read_text().splitlines() if "=" in line
        )
        if not key.startswith("#")
    }
    assert values["SMTP_PASSWORD"] in {"changeme", "your-password-here"}
    assert values["ANTHROPIC_API_KEY"] == "your-key-here"
    assert values["SMTP_HOST"].endswith(".invalid")
