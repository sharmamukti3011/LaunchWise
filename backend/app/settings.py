"""Single validated settings object. The only module that reads environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    cors_allowed_origin: str = "http://localhost:5173"
    database_path: str = "./data/launchwise.db"

    anthropic_api_key: SecretStr | None = None
    claude_model: str | None = None
    claude_max_calls_per_session: int = Field(default=20, ge=1)
    claude_max_calls_global: int = Field(default=500, ge=1)

    smtp_host: str | None = None
    smtp_port: int | None = Field(default=None, ge=0, le=65535)
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    contact_recipient: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
