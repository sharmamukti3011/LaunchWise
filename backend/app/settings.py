"""Single validated settings object. The only module that reads environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# The value shipped in .env.example. Public, so refusing it is a guard, not a credential check.
EXAMPLE_PLACEHOLDER = "changeme"
# The Claude placeholders shipped in .env.example. A copied-but-unedited file must not look enabled.
EXAMPLE_CLAUDE_KEY = "your-key-here"
EXAMPLE_CLAUDE_MODEL = "your-model-name-here"


ContactStatus = Literal["ready", "disabled", "not_configured"]
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
    # SMTP_SSL (port 465) is the default; "none" is refused in production.
    smtp_security: Literal["starttls", "ssl", "none"] = "ssl"
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    contact_recipient: str | None = None
    contact_rate_limit_per_ip: int = Field(default=5, ge=1)
    contact_rate_window_seconds: int = Field(default=3600, ge=1)
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

    @property
    def contact_problems(self) -> list[str]:
        """What stops the contact form from working. Variable names only, never their values."""
        problems: list[str] = []
        for env_name, value in (
            ("SMTP_HOST", self.smtp_host),
            ("SMTP_USER", self.smtp_user),
            ("CONTACT_RECIPIENT", self.contact_recipient),
        ):
            text = (value or "").strip()
            if not text:
                problems.append(f"{env_name} is not set")
            elif text.endswith(".invalid"):
                problems.append(f"{env_name} is still the example placeholder")
        if self.smtp_port is None or self.smtp_port < 1:
            problems.append("SMTP_PORT is not set to a real port (1-65535)")
        password = self.smtp_password.get_secret_value().strip() if self.smtp_password else ""
        if not password:
            problems.append("SMTP_PASSWORD is not set")
        elif password == EXAMPLE_PLACEHOLDER:
            problems.append("SMTP_PASSWORD is still the example placeholder")
        if self.smtp_security == "none" and self.app_env == "production":
            problems.append("SMTP_SECURITY=none is not allowed in production")
        return problems

    @property
    def contact_status(self) -> ContactStatus:
        """Missing mailbox settings never stop the app: the form just answers "not configured"."""
        if self.contact_problems:
            return "not_configured"
        return "ready" if self.contact_enabled else "disabled"


@lru_cache
def get_settings() -> Settings:
    return Settings()
