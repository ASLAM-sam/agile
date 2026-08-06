"""Error handlers must survive the errors they handle.

Regression: `_handle_aegis` logged with `extra={"message": ...}`. `message` is a
reserved `LogRecord` attribute, so `logging` raised `KeyError` inside the
handler itself. Starlette then fell through to the catch-all, and every domain
error of status >= 500 reached the browser as a bare 500 "An unexpected error
occurred" — the status, the error code and the explanation all discarded.

The provider's real message in the case that exposed this was "Your credit
balance is too low", which the user never saw.
"""

from __future__ import annotations

import ast
import logging
import pathlib

import anthropic
import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import (
    AgentExecutionError,
    ConfigurationError,
    LLMError,
    NotFoundError,
    ValidationError,
    WorkflowError,
    register_exception_handlers,
)
from app.llm.client import LLMClient
from app.llm.types import PromptBundle

APP_ROOT = pathlib.Path(__file__).resolve().parents[2] / "app"

#: Names `logging.Logger.makeRecord` refuses to accept in `extra`. It raises
#: KeyError rather than overwriting, so a collision is a crash, not a warning.
RESERVED_LOG_KEYS = set(
    logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None).__dict__
) | {"message", "asctime"}


def reserved_key_usages() -> list[tuple[str, int, str]]:
    """Every `extra={...}` in the application that names a reserved key."""
    found: list[tuple[str, int, str]] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "extra" or not isinstance(keyword.value, ast.Dict):
                    continue
                for key in keyword.value.keys:
                    if isinstance(key, ast.Constant) and key.value in RESERVED_LOG_KEYS:
                        rel = path.relative_to(APP_ROOT.parent).as_posix()
                        found.append((rel, key.lineno, str(key.value)))
    return found


class TestNoReservedLogKeys:
    """A static guard: the collision is invisible until the log line executes."""

    def test_no_extra_dict_uses_a_reserved_key(self) -> None:
        usages = reserved_key_usages()
        assert usages == [], "logging.extra keys collide with LogRecord: " + ", ".join(
            f"{f}:{line} -> {key!r}" for f, line, key in usages
        )

    def test_the_guard_itself_detects_a_known_reserved_name(self) -> None:
        # Guards that cannot fail are decoration. Confirm the reserved set is
        # populated and contains the name that caused the original outage.
        assert "message" in RESERVED_LOG_KEYS
        assert "filename" in RESERVED_LOG_KEYS


@pytest.fixture
def error_client() -> AsyncClient:
    """A minimal app that raises one chosen error per route."""
    app = FastAPI()
    register_exception_handlers(app)

    errors = {
        "llm": LLMError("Your credit balance is too low.", details={"agent": "analyst"}),
        "configuration": ConfigurationError("ANTHROPIC_API_KEY is not configured."),
        "workflow": WorkflowError("The dependency graph contains a cycle."),
        "agent": AgentExecutionError(
            "The Backend Engineer produced no files.", agent="backend_engineer"
        ),
        "not_found": NotFoundError("Project not found."),
        "validation": ValidationError("Idea must not be empty."),
    }

    @app.get("/raise/{key}")
    async def _raise(key: str) -> None:
        raise errors[key]

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://errors")


class TestServerErrorsKeepTheirIdentity:
    """A >=500 domain error must reach the client intact, not as a bare 500."""

    @pytest.mark.parametrize(
        "key, expected_status, expected_code",
        [
            ("llm", 502, "llm_error"),
            ("configuration", 503, "configuration_error"),
            ("workflow", 500, "workflow_error"),
            ("agent", 500, "agent_execution_failed"),
        ],
    )
    async def test_status_and_code_survive_the_handler(
        self, error_client: AsyncClient, key: str, expected_status: int, expected_code: str
    ) -> None:
        async with error_client as client:
            response = await client.get(f"/raise/{key}")
        assert response.status_code == expected_status
        assert response.json()["error"] == expected_code

    async def test_the_explanation_reaches_the_client(self, error_client: AsyncClient) -> None:
        async with error_client as client:
            response = await client.get("/raise/llm")
        body = response.json()
        assert body["message"] == "Your credit balance is too low."
        assert body["message"] != "An unexpected error occurred."

    async def test_details_are_preserved(self, error_client: AsyncClient) -> None:
        async with error_client as client:
            response = await client.get("/raise/llm")
        assert response.json()["details"] == {"agent": "analyst"}

    async def test_logging_a_server_error_does_not_raise(
        self, error_client: AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        # The original failure happened inside logging, so exercise it with the
        # logger actually enabled rather than filtered out.
        with caplog.at_level(logging.ERROR, logger="app.core.exceptions"):
            async with error_client as client:
                response = await client.get("/raise/workflow")
        assert response.status_code == 500
        assert any(record.message == "aegis_error" for record in caplog.records)
        assert any(getattr(record, "code", None) == "workflow_error" for record in caplog.records)


class TestProviderBadRequestTranslation:
    """A provider 400 must say what to do, not echo the response body."""

    def bad_request(self, message: str) -> anthropic.BadRequestError:
        body = {"type": "error", "error": {"type": "invalid_request_error", "message": message}}
        response = httpx.Response(
            400, json=body, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        )
        return anthropic.BadRequestError("400 Bad Request", response=response, body=body)

    def test_the_json_envelope_is_stripped(self) -> None:
        exc = self.bad_request("max_tokens must be greater than 0")
        assert LLMClient._provider_message(exc) == "max_tokens must be greater than 0"

    def test_an_unparseable_body_falls_back_to_the_repr(self) -> None:
        response = httpx.Response(
            400, text="not json", request=httpx.Request("POST", "https://api.anthropic.com/")
        )
        exc = anthropic.BadRequestError("400 Bad Request", response=response, body=None)
        assert LLMClient._provider_message(exc)

    def test_a_depleted_balance_becomes_a_configuration_error(self) -> None:
        # 503 + no traceback: an empty wallet is an account state needing a
        # billing action, not a defect worth a stack trace in the logs.
        translated = LLMClient._translate_bad_request(
            LLMClient.__new__(LLMClient),
            self.bad_request("Your credit balance is too low to access the Anthropic API."),
            PromptBundle(cacheable_system="s", user_message="u"),
        )
        assert isinstance(translated, ConfigurationError)
        assert translated.status_code == 503
        assert translated.log_traceback is False
        assert "credit balance is too low" in translated.message

    def test_a_genuine_request_defect_stays_an_llm_error(self) -> None:
        translated = LLMClient._translate_bad_request(
            LLMClient.__new__(LLMClient),
            self.bad_request("max_tokens must be greater than 0"),
            PromptBundle(cacheable_system="s", user_message="u", metadata={"agent": "analyst"}),
        )
        assert isinstance(translated, LLMError)
        assert translated.status_code == 502
        assert "max_tokens must be greater than 0" in translated.message
        assert translated.details == {"agent": "analyst"}

    def test_the_raw_response_body_is_not_shown_to_the_user(self) -> None:
        translated = LLMClient._translate_bad_request(
            LLMClient.__new__(LLMClient),
            self.bad_request("Your credit balance is too low."),
            PromptBundle(cacheable_system="s", user_message="u"),
        )
        for noise in ("invalid_request_error", "{'type'", "request_id"):
            assert noise not in translated.message


class TestClientErrorsAreNotLogged:
    """A 4xx is the caller's problem; it must not be logged as a server fault."""

    @pytest.mark.parametrize(
        "key, expected_status, expected_code",
        [
            ("not_found", 404, "not_found"),
            ("validation", 422, "validation_error"),
        ],
    )
    async def test_client_errors_pass_through(
        self, error_client: AsyncClient, key: str, expected_status: int, expected_code: str
    ) -> None:
        async with error_client as client:
            response = await client.get(f"/raise/{key}")
        assert response.status_code == expected_status
        assert response.json()["error"] == expected_code

    async def test_nothing_is_logged_at_error_level(
        self, error_client: AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.ERROR, logger="app.core.exceptions"):
            async with error_client as client:
                await client.get("/raise/not_found")
        assert caplog.records == []
