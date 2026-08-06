"""Application configuration.

Single source of truth for runtime settings. Values are read from the
environment (or a `.env` file) and validated once at import time.
"""

from __future__ import annotations

import json
import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

#: `backend/` — this file is `backend/app/core/config.py`.
#:
#: The dotenv path is anchored to the package rather than left relative to the
#: working directory. `uvicorn`, `pytest` and `alembic` are each invoked from
#: somewhere different, and a working-directory-relative path means they read
#: different configuration — or none at all — depending on where the shell
#: happens to be.
BACKEND_ROOT = Path(__file__).resolve().parents[2]

#: Where configuration lives by default.
DEFAULT_ENV_FILE = BACKEND_ROOT / ".env"


def _resolve_env_file() -> Path | None:
    """Locate the dotenv file for this process.

    `AEGIS_ENV_FILE` overrides the default location; setting it to an empty
    value disables the file entirely. The test suite does exactly that, so a
    developer's real `backend/.env` can never change a test outcome.
    """
    override = os.getenv("AEGIS_ENV_FILE")
    if override is None:
        return DEFAULT_ENV_FILE
    return Path(override) if override.strip() else None


#: The file this process actually reads — `DEFAULT_ENV_FILE` unless overridden.
ENV_FILE = _resolve_env_file()


class Settings(BaseSettings):
    """Validated application settings.

    Real environment variables take precedence over `backend/.env`, so the
    Docker Compose stack injects configuration directly and never needs the
    file to be present inside the image.
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application -----------------------------------------------------
    app_name: str = "Aegis AI"
    app_version: str = "1.0.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"

    # --- Security --------------------------------------------------------
    # Blank means "absent", not "an empty signing key". `_guard_production`
    # substitutes a per-process random key in development and rejects the state
    # outright in production.
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 12
    refresh_token_ttl_days: int = 14
    # `NoDecode` is required, not cosmetic. Without it pydantic-settings treats
    # a list field as a complex type and runs `json.loads` on the raw value
    # inside the environment source, before any validator sees it. A perfectly
    # ordinary `CORS_ORIGINS=http://a,http://b` is not JSON, so settings
    # construction fails at import with a decoding error. `NoDecode` hands the
    # raw string to `_split_origins` below, which is what actually knows the
    # format.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
        ]
    )

    # --- Database --------------------------------------------------------
    # PostgreSQL is the platform database of record. A SQLite URL is accepted
    # so the platform boots on a workstation without a Postgres instance; the
    # Docker Compose stack always provisions PostgreSQL.
    database_url: str = "sqlite+aiosqlite:///./aegis.db"
    database_echo: bool = False
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # --- Language model --------------------------------------------------
    # Which provider the agents talk to. Both implement `LLMProvider`, so
    # nothing outside this layer changes when the value does.
    llm_provider: Literal["anthropic", "gemini"] = "anthropic"
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"
    llm_model: str = "claude-opus-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    llm_max_tokens: int = 32000
    llm_max_retries: int = 3
    llm_timeout_seconds: float = 900.0

    # --- Generation limits ----------------------------------------------
    max_concurrent_runs: int = 4
    max_files_per_project: int = 400
    max_file_bytes: int = 512_000
    generation_batch_size: int = 4
    artifact_root: str = "./artifacts"
    artifact_retention_days: int = 30

    # --- Bootstrap admin -------------------------------------------------
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Parse `CORS_ORIGINS` from the forms people actually write.

        Comma-separated is the documented format. A JSON array is accepted too,
        because that is what pydantic-settings would have expected by default
        and it is a reasonable thing to try.
        """
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass  # Fall through and treat it as a plain list.
        return [origin.strip() for origin in text.split(",") if origin.strip()]

    @field_validator(
        "anthropic_api_key",
        "google_api_key",
        "bootstrap_admin_email",
        "bootstrap_admin_password",
    )
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        """Treat the empty placeholders in `.env.example` as unset."""
        if value is not None and not value.strip():
            return None
        return value

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        """Coerce sync driver URLs to their async equivalents."""
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("sqlite://") and "+aiosqlite" not in value:
            return value.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return value

    @model_validator(mode="after")
    def _guard_production(self) -> Settings:
        secret_provided = bool(self.secret_key.strip())

        if self.environment == "production":
            if self.debug:
                raise ValueError("debug must be disabled in production")
            if self.database_url.startswith("sqlite"):
                raise ValueError("production requires a PostgreSQL database_url")
            if not secret_provided:
                raise ValueError(
                    "production requires an explicit SECRET_KEY; generate one with "
                    "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
                )
            if len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must be at least 32 characters")

        if not secret_provided:
            # A `.env` copied from the example has `SECRET_KEY=` with nothing
            # after it, which pydantic reads as the empty string. Left alone
            # that signs every JWT with a zero-length key. Generating one keeps
            # the failure loud — sessions drop on restart — instead of silent.
            self.secret_key = secrets.token_urlsafe(48)

        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def llm_configured(self) -> bool:
        """Whether the *selected* provider has the key it needs."""
        if self.llm_provider == "gemini":
            return bool(self.google_api_key)
        return bool(self.anthropic_api_key)

    @property
    def active_model(self) -> str:
        """The model identifier the selected provider will use."""
        return self.gemini_model if self.llm_provider == "gemini" else self.llm_model

    @property
    def active_api_key_variable(self) -> str:
        """The environment variable a user must set for the selected provider."""
        return "GOOGLE_API_KEY" if self.llm_provider == "gemini" else "ANTHROPIC_API_KEY"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


settings = get_settings()
