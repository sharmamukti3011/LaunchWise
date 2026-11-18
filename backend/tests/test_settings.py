"""Settings defaults and the .env.example that documents them."""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

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
    assert values["SMTP_USER"].endswith(".invalid") and values["CONTACT_RECIPIENT"].endswith(
        ".invalid"
    )


def test_env_example_describes_the_titan_ssl_mailbox_without_real_credentials() -> None:
    text = ENV_EXAMPLE.read_text()
    values = dict(
        line.split("=", 1) for line in text.splitlines() if "=" in line and not line.startswith("#")
    )
    assert (values["SMTP_HOST"], values["SMTP_PORT"], values["SMTP_SECURITY"]) == (
        "smtp.titan.email",
        "465",
        "ssl",
    )
    assert values["CONTACT_RATE_LIMIT_PER_IP"] == "5"
    assert values["CONTACT_RATE_WINDOW_SECONDS"] == "3600"


# ---- contact settings and the production validator --------------------------------------------

REAL_LOOKING = {
    "smtp_host": "smtp.mail.test",
    "smtp_port": 587,
    "smtp_user": "owner@mail.test",
    "smtp_password": "s3cret-value-xyz",
    "contact_recipient": "owner@mail.test",
}


def production(**overrides: object) -> Settings:
    data: dict[str, object] = {"app_env": "production", "contact_enabled": True, **REAL_LOOKING}
    data.update(overrides)
    return Settings(_env_file=None, **data)  # type: ignore[arg-type]


def test_contact_defaults_are_conservative() -> None:
    settings = Settings(_env_file=None)
    assert settings.smtp_security == "ssl"
    assert settings.contact_rate_limit_per_ip == 5
    assert settings.contact_rate_window_seconds == 3600  # five per hour
    assert settings.contact_rate_limit_global == 200
    assert settings.contact_rate_window_global_seconds == 3600  # the global cap is per hour


def test_analyze_is_limited_to_60_requests_a_minute_per_client_by_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.analyze_rate_limit_per_ip == 60
    assert settings.analyze_rate_window_seconds == 60


@pytest.mark.parametrize("field", ["analyze_rate_limit_per_ip", "analyze_rate_window_seconds"])
def test_analyze_rate_limit_settings_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: 0})  # type: ignore[arg-type]


def test_production_with_contact_disabled_needs_no_mailbox_values() -> None:
    # The first deploy must work before Titan details exist.
    settings = Settings(_env_file=None, app_env="production", contact_enabled=False)
    assert settings.contact_enabled is False


def test_production_with_contact_enabled_and_real_values_is_accepted() -> None:
    assert production().contact_enabled is True


@pytest.mark.parametrize(
    "env_name", ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "contact_recipient"]
)
def test_a_missing_mailbox_value_makes_contact_not_configured_without_stopping_startup(
    env_name: str,
) -> None:
    settings = production(**{env_name: None})  # no exception: the app must still boot
    assert settings.contact_status == "not_configured"
    assert any(env_name.upper() in problem for problem in settings.contact_problems)


def test_blank_values_count_as_missing() -> None:
    settings = production(smtp_host="  ")
    assert settings.contact_status == "not_configured"
    assert "SMTP_HOST is not set" in settings.contact_problems


@pytest.mark.parametrize(
    ("overrides", "needle"),
    [
        ({"smtp_port": 0}, "SMTP_PORT"),
        ({"smtp_host": "smtp.example.invalid"}, "SMTP_HOST is still the example placeholder"),
        ({"smtp_user": "me@example.invalid"}, "SMTP_USER is still the example placeholder"),
        ({"smtp_password": "changeme"}, "SMTP_PASSWORD is still the example placeholder"),
        ({"contact_recipient": "x@example.invalid"}, "CONTACT_RECIPIENT is still"),
    ],
)
def test_the_example_placeholders_count_as_not_configured(
    overrides: dict[str, object], needle: str
) -> None:
    settings = production(**overrides)
    assert settings.contact_status == "not_configured"
    assert any(needle in problem for problem in settings.contact_problems)


def test_a_complete_enabled_mailbox_is_ready_and_a_disabled_one_is_disabled() -> None:
    assert production().contact_status == "ready" and production().contact_problems == []
    assert production(contact_enabled=False).contact_status == "disabled"


def test_with_nothing_set_contact_is_not_configured_and_names_every_missing_variable() -> None:
    settings = Settings(_env_file=None)
    assert settings.contact_status == "not_configured"
    named = " ".join(settings.contact_problems)
    for name in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "CONTACT_RECIPIENT"):
        assert name in named


def test_problems_name_variables_never_their_values() -> None:
    settings = production(smtp_host="smtp.example.invalid", smtp_password="changeme")
    text = " ".join(settings.contact_problems)
    for value in ("smtp.example.invalid", "changeme", "s3cret-value-xyz", "owner@mail.test"):
        assert value not in text


def test_unencrypted_smtp_in_production_is_not_configured_not_a_crash() -> None:
    settings = production(smtp_security="none")
    assert settings.contact_status == "not_configured"
    assert any("SMTP_SECURITY" in problem for problem in settings.contact_problems)


@pytest.mark.parametrize("mode", ["starttls", "ssl"])
def test_production_allows_encrypted_smtp_modes(mode: str) -> None:
    settings = production(smtp_security=mode)
    assert settings.smtp_security == mode and settings.contact_status == "ready"


@pytest.mark.parametrize("env", ["development", "test"])
def test_outside_production_contact_can_be_enabled_without_mailbox_values(env: str) -> None:
    settings = Settings(_env_file=None, app_env=env, contact_enabled=True)
    assert settings.contact_enabled is True


def test_unknown_smtp_security_mode_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, smtp_security="plaintext")


@pytest.mark.parametrize(
    "field",
    [
        "contact_rate_limit_per_ip",
        "contact_rate_window_seconds",
        "contact_rate_limit_global",
        "contact_rate_window_global_seconds",
    ],
)
def test_rate_limit_settings_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: 0})  # type: ignore[arg-type]


def test_password_never_appears_in_repr_str_dumps_or_validation_errors() -> None:
    settings = production()
    for text in (
        repr(settings),
        str(settings),
        settings.model_dump_json(),
        str(settings.model_dump()),
    ):
        assert "s3cret-value-xyz" not in text
    assert settings.smtp_password is not None
    assert settings.smtp_password.get_secret_value() == "s3cret-value-xyz"
    assert "s3cret-value-xyz" not in " ".join(production(smtp_host=None).contact_problems)
