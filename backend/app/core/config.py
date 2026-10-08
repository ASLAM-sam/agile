"""Application configuration.

Single source of truth for runtime settings. Values are read from the
environment (or a `.env` file) and validated once at import time.

Authoritative 7 Dedicated Gemini Credential Slots (01 Suffix):
  1. PLANNER_API_KEY01      → Manager, Business Analyst, Solution Architect
  2. FRONTEND_API_KEY01     → Frontend Engineer, Documentation Engineer
  3. BACKEND_API_KEY01      → Backend Engineer
  4. DATABASE_API_KEY01     → Database Engineer
  5. QA_API_KEY01           → QA Engineer
  6. REVIEW_API_KEY01       → Review Engineer, Improvement Engineer
  7. DEBUG_API_KEY01        → Final QA Agent, Self-repair/debug functionality
  Artifact Manager          → Deterministic (Zero LLM calls)
Model: gemini-3.6-flash ONLY
"""

from __future__ import annotations

import json
import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
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
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 12
    refresh_token_ttl_days: int = 14
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
        ]
    )

    # --- Database --------------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///./aegis.db"
    database_echo: bool = False
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # --- Authoritative 7 Dedicated Credential Slots (01 Suffix) -----------
    planner_api_key01: str | None = None
    frontend_api_key01: str | None = None
    backend_api_key01: str | None = None
    database_api_key01: str | None = None
    qa_api_key01: str | None = None
    review_api_key01: str | None = None
    debug_api_key01: str | None = None

    # --- 7-Slot Authoritative Model Configuration ------------------------
    planner_model: str = Field(
        default="nvidia/nemotron-3-super-120b-a12b",
        validation_alias=AliasChoices("planner_model", "planner_api_key01_model"),
    )
    frontend_model: str = Field(
        default="gemini-3.6-flash",
        validation_alias=AliasChoices("frontend_model", "frontend_api_key01_model"),
    )
    backend_model: str = Field(
        default="gemini-3.6-flash",
        validation_alias=AliasChoices("backend_model", "backend_api_key01_model"),
    )
    database_model: str = Field(
        default="gemini-3.6-flash",
        validation_alias=AliasChoices("database_model", "database_api_key01_model"),
    )
    qa_model: str = Field(
        default="nvidia/nemotron-3-super-120b-a12b",
        validation_alias=AliasChoices("qa_model", "qa_api_key01_model"),
    )
    review_model: str = Field(
        default="nvidia/nemotron-3-super-120b-a12b",
        validation_alias=AliasChoices("review_model", "review_api_key01_model"),
    )
    debug_model: str = Field(
        default="nvidia/nemotron-3-super-120b-a12b",
        validation_alias=AliasChoices("debug_model", "debug_api_key01_model"),
    )

    # --- NVIDIA NIM Configuration ----------------------------------------
    nvidia_api_key: str | None = None
    nvidia_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        validation_alias=AliasChoices("nvidia_base_url", "nvidia_api_base_url"),
    )
    nvidia_model: str = Field(
        default="nvidia/nemotron-3-super-120b-a12b",
        validation_alias=AliasChoices("nvidia_model"),
    )

    # --- Default Provider and Model Configuration ------------------------
    default_provider: str = Field(
        default="gemini",
        validation_alias=AliasChoices("default_provider", "default_llm_provider"),
    )
    default_model: str = Field(
        default="gemini-3.6-flash",
        validation_alias=AliasChoices("default_model", "default_llm_model"),
    )

    # --- OpenAI Provider Configuration -----------------------------------
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # --- Mistral Provider Configuration ----------------------------------
    mistral_api_key: str | None = None
    mistral_base_url: str = "https://api.mistral.ai/v1"
    mistral_model: str = "mistral-large-latest"

    # --- GitHub Models Provider Configuration ----------------------------
    github_token: str | None = None
    github_models_token: str | None = None
    github_models_base_url: str = "https://models.inference.ai.azure.com"
    github_models_model: str = "gpt-4o"

    # --- Groq Provider Configuration -------------------------------------
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"

    # --- Optional SiliconFlow Configuration ------------------------------
    siliconflow_api_key: str | None = None
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "Qwen/Qwen2.5-7B-Instruct"

    # --- Per-Task Request Budget -----------------------------------------
    target_requests_per_task: int = Field(
        default=10,
        validation_alias=AliasChoices("target_requests_per_task", "llm_request_target"),
    )
    hard_max_requests_per_task: int = Field(
        default=15,
        validation_alias=AliasChoices("hard_max_requests_per_task", "llm_request_hard_max"),
    )

    # --- Frontend Stack Configuration ------------------------------------
    default_frontend_stack: str = "html_css_js"  # html_css_js, react, nextjs

    # --- Authoritative Centralized Gemini Model Configuration -------------
    gemini_model: str = "gemini-3.6-flash"
    gemini_allowed_model: str = "gemini-3.6-flash"
    gemini_fallback_models: list[str] = Field(
        default_factory=lambda: ["gemini-3.6-flash"]
    )
    gemini_priority: int = 1

    # --- DeepSeek provider configuration ---------------------------------
    deepseek_enabled: bool = False
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_primary_model: str = "deepseek-flash"
    deepseek_fallback_model: str = "deepseek-v4-pro"
    deepseek_thinking_effort: str = "low"
    deepseek_priority: int = 2

    # --- SambaNova provider configuration --------------------------------
    sambanova_enabled: bool = False
    sambanova_api_key: str | None = None
    sambanova_base_url: str = "https://api.sambanova.ai/v1"
    sambanova_primary_model: str = "YOUR_SAMBANOVA_MODEL_ID"
    sambanova_priority: int = 3

    # --- Generation limits ----------------------------------------------
    max_concurrent_runs: int = 4
    max_files_per_project: int = 400
    max_file_bytes: int = 512_000
    generation_batch_size: int = 4
    artifact_root: str = "./artifacts"
    artifact_retention_days: int = 30
    max_repair_cycles: int = 5

    # --- LLM shared settings -------------------------------------------
    llm_max_tokens: int = 32000
    llm_max_retries: int = 3
    llm_timeout_seconds: float = 900.0
    llm_cache_enabled: bool = True
    llm_cache_max_entries: int = 512
    llm_cache_ttl_seconds: float = 3600.0
    llm_quota_cooldown_seconds: float = 300.0
    llm_failure_cooldown_seconds: float = 60.0
    llm_failure_threshold: int = 3

    # Intent pre-check (non-software briefs rejected before agents run)
    intent_check_enabled: bool = True

    # --- Bootstrap admin -------------------------------------------------
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return [origin.strip() for origin in text.split(",") if origin.strip()]

    @field_validator(
        "planner_api_key01",
        "frontend_api_key01",
        "backend_api_key01",
        "database_api_key01",
        "qa_api_key01",
        "review_api_key01",
        "debug_api_key01",
        "nvidia_api_key",
        "openai_api_key",
        "mistral_api_key",
        "github_token",
        "github_models_token",
        "groq_api_key",
        "deepseek_api_key",
        "sambanova_api_key",
        "bootstrap_admin_email",
        "bootstrap_admin_password",
    )
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        """Treat the empty placeholders in `.env.example` as unset."""
        if value is not None and not value.strip():
            return None
        return value

    @field_validator("debug", mode="before")
    @classmethod
    def _parse_debug(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalised = value.strip().lower()
        if normalised in {"debug", "development", "dev"}:
            return True
        if normalised in {"release", "production", "prod"}:
            return False
        return value

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
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
                    'python -c "import secrets; print(secrets.token_urlsafe(48))"'
                )
            if len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must be at least 32 characters")

        if not secret_provided:
            self.secret_key = secrets.token_urlsafe(48)

        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def get_backup_credentials(self) -> list[str]:
        """Backup API key pool is removed. Each role has a dedicated Gemini slot."""
        return []

    def get_role_credential(self, role: str) -> str | None:
        """Resolve credential for an agent role using the 7 dedicated Gemini slots."""
        normalized = role.lower().replace("-", "_")
        if "artifact_manager" in normalized:
            return None
        key: str | None = None
        if (
            "planner" in normalized
            or "manager" in normalized
            or "analyst" in normalized
            or "architect" in normalized
        ):
            key = self.planner_api_key01
        elif "frontend" in normalized or "documentation" in normalized or "doc" in normalized:
            key = self.frontend_api_key01
        elif "backend" in normalized:
            key = self.backend_api_key01
        elif "database" in normalized:
            key = self.database_api_key01
        elif "final_qa" in normalized or "debug" in normalized or "repair" in normalized:
            key = self.debug_api_key01
        elif "qa" in normalized:
            key = self.qa_api_key01
        elif "review" in normalized or "improvement" in normalized:
            key = self.review_api_key01

        if not key and getattr(self, "siliconflow_api_key", None):
            key = self.siliconflow_api_key

        return key.strip() if key and key.strip() else None

    def get_slot_model(self, slot: str) -> str:
        """Resolve the model name for a credential slot from separate model config."""
        s = slot.upper().strip()
        models = {
            "PLANNER_API_KEY01": self.planner_model,
            "FRONTEND_API_KEY01": self.frontend_model,
            "BACKEND_API_KEY01": self.backend_model,
            "DATABASE_API_KEY01": self.database_model,
            "QA_API_KEY01": self.qa_model,
            "REVIEW_API_KEY01": self.review_model,
            "DEBUG_API_KEY01": self.debug_model,
        }
        return models.get(s, self.default_model)

    def get_role_model(self, role: str) -> str:
        """Resolve the configured model for an agent role."""
        normalized = role.lower().replace("-", "_")
        if "artifact_manager" in normalized:
            return "deterministic"
        if (
            "planner" in normalized
            or "manager" in normalized
            or "analyst" in normalized
            or "architect" in normalized
        ):
            return self.planner_model
        if "frontend" in normalized or "documentation" in normalized or "doc" in normalized:
            return self.frontend_model
        if "backend" in normalized:
            return self.backend_model
        if "database" in normalized:
            return self.database_model
        if "final_qa" in normalized or "debug" in normalized or "repair" in normalized:
            return self.debug_model
        if "qa" in normalized:
            return self.qa_model
        if "review" in normalized or "improvement" in normalized:
            return self.review_model
        return self.default_model

    @property
    def llm_configured(self) -> bool:
        """Whether at least one of the 7 dedicated role slots is configured."""
        return any([
            self.planner_api_key01,
            self.frontend_api_key01,
            self.backend_api_key01,
            self.database_api_key01,
            self.qa_api_key01,
            self.review_api_key01,
            self.debug_api_key01,
            self.openai_api_key,
            self.mistral_api_key,
            self.github_token,
            self.groq_api_key,
            self.deepseek_api_key,
            self.sambanova_api_key,
            self.siliconflow_api_key,
        ])

    @property
    def active_model(self) -> str:
        """The primary configured model (for health display only)."""
        return self.gemini_model

    @property
    def active_api_key_variable(self) -> str:
        """Environment variable hint for the UI config guide."""
        if self.frontend_api_key01:
            return "FRONTEND_API_KEY01"
        if self.planner_api_key01:
            return "PLANNER_API_KEY01"
        if self.backend_api_key01:
            return "BACKEND_API_KEY01"
        return "FRONTEND_API_KEY01"

    def validate_gemini_credentials(self) -> dict[str, Any]:
        """Audit the 7 dedicated Gemini credential slots for uniqueness and validity without exposing secrets."""
        import hashlib

        slots = {
            "PLANNER_API_KEY01": self.planner_api_key01,
            "FRONTEND_API_KEY01": self.frontend_api_key01,
            "BACKEND_API_KEY01": self.backend_api_key01,
            "DATABASE_API_KEY01": self.database_api_key01,
            "QA_API_KEY01": self.qa_api_key01,
            "REVIEW_API_KEY01": self.review_api_key01,
            "DEBUG_API_KEY01": self.debug_api_key01,
        }
        seen: dict[str, str] = {}
        duplicates: list[tuple[str, str]] = []
        configured: list[str] = []

        for slot, key in slots.items():
            if key and key.strip():
                configured.append(slot)
                digest = hashlib.sha256(key.strip().encode("utf-8")).hexdigest()[:16]
                if digest in seen:
                    duplicates.append((slot, seen[digest]))
                else:
                    seen[digest] = slot

        return {
            "configured_count": len(configured),
            "configured_slots": configured,
            "valid_count": len(seen),
            "duplicate_count": len(duplicates),
            "duplicate_slots": duplicates,
            "missing_count": max(0, 7 - len(configured)),
            "failover_enabled": False,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


settings = get_settings()
