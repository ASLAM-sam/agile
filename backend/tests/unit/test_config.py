"""Settings parsing and safety guards.

Every case here corresponds to a `.env` a person actually writes. The two
regression classes cover failures that a `.env` copied verbatim from
`.env.example` triggers on the very first run.

Overrides are applied to the process environment rather than passed as
constructor arguments. That is deliberate: the bugs being guarded against live
in the environment source's decoding step, which init kwargs bypass entirely.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import BACKEND_ROOT, DEFAULT_ENV_FILE, ENV_FILE, Settings, _resolve_env_file

#: Cleared before each construction so an ambient shell variable cannot change
#: a result. Every variable any test in this module sets must appear here.
MANAGED_VARIABLES = (
    "ANTHROPIC_API_KEY",
    "BOOTSTRAP_ADMIN_EMAIL",
    "BOOTSTRAP_ADMIN_PASSWORD",
    "CORS_ORIGINS",
    "DATABASE_URL",
    "DEBUG",
    "ENVIRONMENT",
    "LOG_FORMAT",
    "LOG_LEVEL",
    "SECRET_KEY",
)

SettingsBuilder = Callable[..., Settings]


@pytest.fixture
def build(monkeypatch: pytest.MonkeyPatch) -> SettingsBuilder:
    """Build `Settings` from a clean environment plus the given variables.

    `_env_file=None` disables the dotenv source so a developer's real
    `backend/.env` cannot influence the outcome.
    """

    def _build(**environment: str) -> Settings:
        for name in MANAGED_VARIABLES:
            monkeypatch.delenv(name, raising=False)
        for name, value in environment.items():
            monkeypatch.setenv(name, value)
        return Settings(_env_file=None)

    return _build


class TestEnvFileLocation:
    """The dotenv path is anchored to the backend package, not the shell's cwd."""

    def test_default_is_absolute(self) -> None:
        assert DEFAULT_ENV_FILE.is_absolute()

    def test_default_lives_in_the_backend_root(self) -> None:
        assert DEFAULT_ENV_FILE.name == ".env"
        assert DEFAULT_ENV_FILE.parent == BACKEND_ROOT
        assert BACKEND_ROOT.name == "backend"

    def test_backend_root_contains_the_application_package(self) -> None:
        assert (BACKEND_ROOT / "app" / "core" / "config.py").is_file()

    def test_the_example_sits_beside_it(self) -> None:
        assert (BACKEND_ROOT / ".env.example").is_file()


class TestEnvFileOverride:
    """`AEGIS_ENV_FILE` redirects or disables the dotenv source."""

    def test_the_suite_runs_with_the_dotenv_source_disabled(self) -> None:
        # conftest sets AEGIS_ENV_FILE="" before importing the application, so
        # a developer's real backend/.env cannot influence any test.
        assert ENV_FILE is None

    def test_unset_resolves_to_the_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AEGIS_ENV_FILE", raising=False)
        assert _resolve_env_file() == DEFAULT_ENV_FILE

    def test_blank_disables_the_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AEGIS_ENV_FILE", "")
        assert _resolve_env_file() is None

    def test_whitespace_disables_the_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AEGIS_ENV_FILE", "  ")
        assert _resolve_env_file() is None

    def test_a_path_is_honoured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AEGIS_ENV_FILE", "/etc/aegis/staging.env")
        assert _resolve_env_file() == Path("/etc/aegis/staging.env")


class TestCorsOriginParsing:
    """A comma-separated `CORS_ORIGINS` must not be JSON-decoded by the source.

    Regression: pydantic-settings treats `list[str]` as a complex type and runs
    `json.loads` on the raw environment value before any validator sees it. The
    documented comma-separated form is not JSON, so settings construction died
    at import the first time a real `.env` existed. `NoDecode` on the field is
    what keeps this passing.
    """

    def test_comma_separated(self, build: SettingsBuilder) -> None:
        settings = build(CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173")
        assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]

    def test_whitespace_is_trimmed_and_blanks_dropped(self, build: SettingsBuilder) -> None:
        assert build(CORS_ORIGINS=" http://a , , http://b ,").cors_origins == [
            "http://a",
            "http://b",
        ]

    def test_single_origin(self, build: SettingsBuilder) -> None:
        assert build(CORS_ORIGINS="http://a").cors_origins == ["http://a"]

    def test_json_array_is_also_accepted(self, build: SettingsBuilder) -> None:
        settings = build(CORS_ORIGINS='["http://a", "http://b"]')
        assert settings.cors_origins == ["http://a", "http://b"]

    def test_malformed_json_falls_back_to_splitting(self, build: SettingsBuilder) -> None:
        assert build(CORS_ORIGINS="[http://a,http://b").cors_origins == [
            "[http://a",
            "http://b",
        ]

    def test_a_real_list_passes_through(self) -> None:
        settings = Settings(_env_file=None, cors_origins=["http://a"])
        assert settings.cors_origins == ["http://a"]

    def test_default_covers_the_vite_ports(self, build: SettingsBuilder) -> None:
        assert "http://localhost:5173" in build().cors_origins


class TestSecretKey:
    """A blank `SECRET_KEY=` must never become the signing key.

    Regression: `.env.example` ships `SECRET_KEY=` with nothing after it.
    Pydantic reads that as the empty string, which overrode the generated
    default — every JWT would have been signed with a zero-length key.
    """

    def test_blank_is_replaced_with_a_strong_random_key(self, build: SettingsBuilder) -> None:
        assert len(build(SECRET_KEY="").secret_key) >= 32

    def test_whitespace_only_is_replaced(self, build: SettingsBuilder) -> None:
        assert len(build(SECRET_KEY="   ").secret_key) >= 32

    def test_absent_is_replaced(self, build: SettingsBuilder) -> None:
        assert len(build().secret_key) >= 32

    def test_generated_keys_differ_between_instances(self, build: SettingsBuilder) -> None:
        assert build(SECRET_KEY="").secret_key != build(SECRET_KEY="").secret_key

    def test_an_explicit_key_is_preserved_exactly(self, build: SettingsBuilder) -> None:
        explicit = "x" * 48
        assert build(SECRET_KEY=explicit).secret_key == explicit


class TestBlankOptionalsBecomeNone:
    """`.env.example` leaves optional keys empty; empty is not a value."""

    @pytest.mark.parametrize(
        "variable, attribute",
        [
            ("ANTHROPIC_API_KEY", "anthropic_api_key"),
            ("BOOTSTRAP_ADMIN_EMAIL", "bootstrap_admin_email"),
            ("BOOTSTRAP_ADMIN_PASSWORD", "bootstrap_admin_password"),
        ],
    )
    def test_blank_reads_as_none(
        self, build: SettingsBuilder, variable: str, attribute: str
    ) -> None:
        assert getattr(build(**{variable: ""}), attribute) is None

    def test_llm_is_not_configured_when_the_key_is_blank(self, build: SettingsBuilder) -> None:
        assert build(ANTHROPIC_API_KEY="").llm_configured is False

    def test_llm_is_configured_when_a_key_is_present(self, build: SettingsBuilder) -> None:
        assert build(ANTHROPIC_API_KEY="sk-ant-test").llm_configured is True


class TestDatabaseUrlNormalisation:
    """Sync driver URLs are coerced to their async equivalents."""

    @pytest.mark.parametrize(
        "given, expected",
        [
            ("postgresql://u:p@h:5432/d", "postgresql+asyncpg://u:p@h:5432/d"),
            ("postgres://u:p@h:5432/d", "postgresql+asyncpg://u:p@h:5432/d"),
            ("sqlite:///./aegis.db", "sqlite+aiosqlite:///./aegis.db"),
            ("postgresql+asyncpg://u:p@h:5432/d", "postgresql+asyncpg://u:p@h:5432/d"),
            ("sqlite+aiosqlite:///./aegis.db", "sqlite+aiosqlite:///./aegis.db"),
        ],
    )
    def test_normalisation(self, build: SettingsBuilder, given: str, expected: str) -> None:
        assert build(DATABASE_URL=given).database_url == expected

    def test_is_sqlite_reflects_the_normalised_url(self, build: SettingsBuilder) -> None:
        assert build(DATABASE_URL="sqlite:///./x.db").is_sqlite is True
        assert build(DATABASE_URL="postgresql://u:p@h/d").is_sqlite is False


class TestProductionGuards:
    """Production rejects the configurations that are fine in development."""

    def production(self, build: SettingsBuilder, **overrides: str) -> Settings:
        environment = {
            "ENVIRONMENT": "production",
            "DEBUG": "false",
            "DATABASE_URL": "postgresql+asyncpg://u:p@h:5432/d",
            "SECRET_KEY": "k" * 48,
        }
        environment.update(overrides)
        return build(**environment)

    def test_a_valid_production_configuration_is_accepted(self, build: SettingsBuilder) -> None:
        assert self.production(build).environment == "production"

    def test_debug_is_rejected(self, build: SettingsBuilder) -> None:
        with pytest.raises(ValidationError, match="debug must be disabled"):
            self.production(build, DEBUG="true")

    def test_sqlite_is_rejected(self, build: SettingsBuilder) -> None:
        with pytest.raises(ValidationError, match="PostgreSQL"):
            self.production(build, DATABASE_URL="sqlite+aiosqlite:///./aegis.db")

    def test_a_blank_secret_is_rejected_rather_than_generated(
        self, build: SettingsBuilder
    ) -> None:
        with pytest.raises(ValidationError, match="explicit SECRET_KEY"):
            self.production(build, SECRET_KEY="")

    def test_a_short_secret_is_rejected(self, build: SettingsBuilder) -> None:
        with pytest.raises(ValidationError, match="at least 32 characters"):
            self.production(build, SECRET_KEY="short")

    def test_development_tolerates_all_of_the_above(self, build: SettingsBuilder) -> None:
        settings = build(
            ENVIRONMENT="development",
            DEBUG="true",
            DATABASE_URL="sqlite+aiosqlite:///./aegis.db",
            SECRET_KEY="",
        )
        assert settings.is_sqlite
        assert len(settings.secret_key) >= 32
