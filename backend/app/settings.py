"""Single validated settings object. The only module that reads environment variables."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The value shipped in .env.example. Public, so refusing it is a guard, not a credential check.
EXAMPLE_PLACEHOLDER = "changeme"
# The Claude placeholders shipped in .env.example. A copied-but-unedited file must not look enabled.
EXAMPLE_CLAUDE_KEY = "your-key-here"
EXAMPLE_CLAUDE_MODEL = "your-model-name-here"


ClaudeStatus = Literal[
    "enabled", "missing_key", "placeholder_key", "missing_model", "placeholder_model"
]


class Settings(BaseSettings):
    # hide_input_in_errors keeps raw values (the mailbox password) out of startup error messages.
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["development", "test", "production"] = "development"
    cors_allowed_origin: str = "http://localhost:5173"
    database_path: str = "./data/launchwise.db"

    anthropic_api_key: SecretStr | None = None
    claude_model: str | None = None
    claude_max_calls_per_session: int = Field(default=20, ge=1)
    claude_max_calls_global: int = Field(default=500, ge=1)

    # Off by default so a first deploy needs no mailbox values.
    contact_enabled: bool = False
    smtp_host: str | None = None
    smtp_port: int | None = Field(default=None, ge=0, le=65535)
    # TODO(verify): which mode Titan uses (starttls or ssl); "none" is refused in production.
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    contact_recipient: str | None = None
    contact_rate_limit_per_ip: int = Field(default=5, ge=1)
    contact_rate_window_seconds: int = Field(default=600, ge=1)
    # POST /api/analyze: per visitor address. Cheap and deterministic, so the default is generous.
    analyze_rate_limit_per_ip: int = Field(default=60, ge=1)
    analyze_rate_window_seconds: int = Field(default=60, ge=1)
    # Across all visitors, per hour. Raise it in .env when real traffic needs it; no code change.
    contact_rate_limit_global: int = Field(default=200, ge=1)
    contact_rate_window_global_seconds: int = Field(default=3600, ge=1)

    @property
    def claude_status(self) -> ClaudeStatus:
        """Why Claude explain is on or off. Never carries the key or the model name."""
        key = self.anthropic_api_key.get_secret_value().strip() if self.anthropic_api_key else ""
        model = (self.claude_model or "").strip()
        if not key:
            return "missing_key"
        if key == EXAMPLE_CLAUDE_KEY:
            return "placeholder_key"
        if not model:
            return "missing_model"
        if model == EXAMPLE_CLAUDE_MODEL:
            return "placeholder_model"
        return "enabled"

    @property
    def claude_enabled(self) -> bool:
        """True only with a real key and a model name; otherwise explanations use the template."""
        return self.claude_status == "enabled"

    @model_validator(mode="after")
    def _contact_needs_a_real_mailbox_in_production(self) -> Self:
        """Fail at startup, not on the first visitor's message. Only when the form is enabled."""
        if not (self.contact_enabled and self.app_env == "production"):
            return self
        problems: list[str] = []
        for name in ("smtp_host", "smtp_user", "contact_recipient"):
            value = getattr(self, name)
            if value is None or not value.strip():
                problems.append(f"{name.upper()} is required")
            elif value.strip().endswith(".invalid"):
                problems.append(f"{name.upper()} is still the example placeholder")
        if self.smtp_port is None or self.smtp_port < 1:
            problems.append("SMTP_PORT must be a real port (1-65535)")
        password = self.smtp_password.get_secret_value().strip() if self.smtp_password else ""
        if not password:
            problems.append("SMTP_PASSWORD is required")
        elif password == EXAMPLE_PLACEHOLDER:
            problems.append("SMTP_PASSWORD is still the example placeholder")
        if self.smtp_security == "none":
            problems.append("SMTP_SECURITY=none is not allowed in production")
        if problems:
            # Names only, never values, so a failing startup can't print the password.
            raise ValueError("CONTACT_ENABLED=true in production needs: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
