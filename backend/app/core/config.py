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
    # The preferred provider. It is moved to the front of the routing order
    # rather than being the only option: every other configured provider stays
    # available as a fallback, which is what keeps a run alive when this one
    # hits its quota.
    llm_provider: Literal[
        "anthropic", "gemini", "groq", "nvidia", "openai", "ollama"
    ] = "anthropic"

    #: Fallback order after the preferred provider, most preferred first.
    #: Unknown names are ignored; missing ones simply never get selected.
    llm_provider_priority: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["gemini", "groq", "nvidia", "ollama", "openai", "anthropic"]
    )
    #: Providers switched off regardless of whether they hold credentials.
    llm_disabled_providers: Annotated[list[str], NoDecode] = Field(default_factory=list)

    llm_failover_enabled: bool = True
    llm_task_routing_enabled: bool = True
    #: How long a provider is withheld after a quota or credential rejection.
    llm_quota_cooldown_seconds: float = 300.0
    #: How long a provider is withheld after repeated ordinary failures.
    llm_failure_cooldown_seconds: float = 60.0
    #: Consecutive failures that trigger the shorter cooldown.
    llm_failure_threshold: int = 3

    llm_cache_enabled: bool = True
    llm_cache_max_entries: int = 512
    llm_cache_ttl_seconds: float = 3600.0

    # Per-provider credentials and models.
    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5"

    google_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"

    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # Groq's free tier bills input and output against one per-minute budget
    # (12k TPM by default). These leave headroom under it so a request is
    # skipped rather than rejected.
    groq_max_prompt_tokens: int = 8000
    groq_max_output_tokens: int = 3500

    #: NVIDIA NIM — the hosted catalogue at build.nvidia.com, or a NIM
    #: container running on your own hardware. Both speak the OpenAI
    #: chat-completions protocol, so only the base URL differs.
    nvidia_api_key: str | None = None
    nvidia_model: str = "meta/llama-3.3-70b-instruct"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    # NIM serves a heterogeneous catalogue: context windows run from 8k to
    # beyond 128k depending on which model is configured. Assuming one number
    # for all of them would either strand large prompts on a model that could
    # have held them, or send them to one that cannot. 0 means "no declared
    # limit" — set these to the configured model's real limits when known.
    nvidia_max_prompt_tokens: int = 0
    nvidia_max_output_tokens: int = 0
    #: How this NIM model is asked for JSON. Support varies per model, so it is
    #: configuration rather than an assumption: `json_schema` when the model
    #: enforces a supplied schema, `json_object` when it only guarantees valid
    #: JSON, `prompt` when it does neither. Every mode is validated locally, so
    #: the weakest one is still safe — just less efficient.
    nvidia_structured_output: Literal["json_schema", "json_object", "prompt"] = "json_object"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_max_prompt_tokens: int = 0
    openai_max_output_tokens: int = 0

    #: Ollama runs locally and authenticates nothing, so it needs no key.
    ollama_model: str = "llama3.1"
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_enabled: bool = False
    # Local models usually run with a modest context window.
    ollama_max_prompt_tokens: int = 6000
    ollama_max_output_tokens: int = 4096

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
        "llm_provider_priority", "llm_disabled_providers", mode="before"
    )
    @classmethod
    def _split_provider_list(cls, value: object) -> object:
        """Accept `gemini,groq,ollama` as well as a JSON array.

        Same `NoDecode` reasoning as `cors_origins`: without it the settings
        source tries to JSON-decode a plain comma-separated list and fails
        before any validator runs.
        """
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return [item.strip().lower() for item in text.split(",") if item.strip()]

    @field_validator(
        "anthropic_api_key",
        "google_api_key",
        "groq_api_key",
        "nvidia_api_key",
        "openai_api_key",
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
    def provider_credentials(self) -> dict[str, str | None]:
        """API key per provider. `None` means the provider needs none."""
        return {
            "anthropic": self.anthropic_api_key,
            "gemini": self.google_api_key,
            "groq": self.groq_api_key,
            "nvidia": self.nvidia_api_key,
            "openai": self.openai_api_key,
            "ollama": None,
        }

    @property
    def provider_models(self) -> dict[str, str]:
        return {
            "anthropic": self.llm_model,
            "gemini": self.gemini_model,
            "groq": self.groq_model,
            "nvidia": self.nvidia_model,
            "openai": self.openai_model,
            "ollama": self.ollama_model,
        }

    @property
    def resolved_provider_priority(self) -> list[str]:
        """Routing order: preferred provider first, then the configured list.

        Deduplicated, so naming the preferred provider in the list as well is
        harmless rather than a second attempt at the same one.
        """
        order: list[str] = [self.llm_provider]
        order.extend(self.llm_provider_priority)
        seen: set[str] = set()
        return [key for key in order if not (key in seen or seen.add(key))]

    @property
    def configured_providers(self) -> list[str]:
        """Providers that hold the credentials they need and are switched on."""
        disabled = {key.lower() for key in self.llm_disabled_providers}
        credentials = self.provider_credentials
        available: list[str] = []
        for key in self.resolved_provider_priority:
            if key in disabled or key not in credentials:
                continue
            if key == "ollama":
                if self.ollama_enabled:
                    available.append(key)
                continue
            if credentials[key]:
                available.append(key)
        return available

    @property
    def llm_configured(self) -> bool:
        """Whether at least one provider can serve a request."""
        return bool(self.configured_providers)

    @property
    def active_model(self) -> str:
        """The model the first eligible provider will use."""
        providers = self.configured_providers
        key = providers[0] if providers else self.llm_provider
        return self.provider_models.get(key, self.llm_model)

    @property
    def active_api_key_variable(self) -> str:
        """The environment variable to set for the preferred provider."""
        return {
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GOOGLE_API_KEY",
            "groq": "GROQ_API_KEY",
            "nvidia": "NVIDIA_API_KEY",
            "openai": "OPENAI_API_KEY",
            "ollama": "OLLAMA_ENABLED",
        }.get(self.llm_provider, "ANTHROPIC_API_KEY")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


settings = get_settings()
