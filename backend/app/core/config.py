"""Application settings, read from environment variables (and ``.env`` when present).

Settings are validated at startup so misconfiguration fails fast with an
actionable message instead of at the first request.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from dotenv import find_dotenv, load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    database_url: str = "postgresql+psycopg://eval_user:change_me@localhost:5432/llm_eval"
    redis_url: str = "redis://localhost:6379/0"
    # "celery" enqueues runs on Redis for the worker; "inline" executes them inside the
    # API process and is only meant for tests and quick local experiments.
    run_dispatcher: Literal["celery", "inline"] = "celery"

    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:5173"

    max_cases_per_run: int = Field(default=1000, ge=1, le=100_000)
    max_models_per_run: int = Field(default=10, ge=1, le=50)
    max_request_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)

    # Environment variables a model configuration may reference (API keys, base URLs).
    # Anything else is rejected, so API users cannot make the worker read other secrets.
    provider_env_allowlist: str = (
        "ANTHROPIC_API_KEY,OPENAI_API_KEY,OPENAI_COMPATIBLE_API_KEY,OPENAI_COMPATIBLE_BASE_URL"
    )

    @model_validator(mode="after")
    def _safe_for_environment(self) -> Settings:
        if self.app_env == "production" and self.run_dispatcher == "inline":
            raise ValueError("RUN_DISPATCHER=inline is not allowed when APP_ENV=production")
        return self

    @property
    def provider_env_allowed(self) -> frozenset[str]:
        return frozenset(n.strip() for n in self.provider_env_allowlist.split(",") if n.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_local_env() -> None:
    """Copy variables from the nearest ``.env`` (searching up from the cwd) into ``os.environ``.

    Provider adapters read credentials from the process environment, not from
    ``Settings``, so entry points call this for local runs. Variables that are
    already set always win; without a ``.env`` (e.g. in containers) nothing happens.
    """
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)
