"""Domain exception hierarchy and FastAPI exception handlers."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


class AegisError(Exception):
    """Base class for all application errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"
    #: Whether a 5xx of this type warrants a stack trace. Deliberate,
    #: well-understood states (a missing API key) are logged without one; a
    #: traceback there is noise that trains operators to ignore tracebacks.
    log_traceback: bool = True

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": self.error_code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class NotFoundError(AegisError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"


class ConflictError(AegisError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"


class ValidationError(AegisError):
    # Literal 422 rather than the Starlette constant, whose name changed
    # between releases (`..._UNPROCESSABLE_ENTITY` -> `..._UNPROCESSABLE_CONTENT`).
    status_code = 422
    error_code = "validation_error"


class AuthenticationError(AegisError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "authentication_failed"


class AuthorizationError(AegisError):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "forbidden"


class RateLimitError(AegisError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "rate_limited"


class ConfigurationError(AegisError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "configuration_error"
    log_traceback = False  # the message states the fix; a trace adds nothing


class LLMError(AegisError):
    """Raised when the language model provider fails irrecoverably."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "llm_error"


class AgentExecutionError(AegisError):
    """Raised when an agent cannot produce a valid result."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "agent_execution_failed"

    def __init__(
        self, message: str, *, agent: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message, details={**(details or {}), "agent": agent})
        self.agent = agent


class WorkflowError(AegisError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "workflow_error"


class AdapterNotFoundError(AegisError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "adapter_not_found"


def register_exception_handlers(app: FastAPI) -> None:
    """Attach JSON error handlers so every failure has a stable shape."""

    @app.exception_handler(AegisError)
    async def _handle_aegis(_: Request, exc: AegisError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error(
                "aegis_error",
                # Not `message`: logging reserves that name on LogRecord and
                # raises KeyError for it, which would crash this handler and
                # downgrade a precise domain error into a generic 500.
                extra={"code": exc.error_code, "reason": exc.message},
                exc_info=exc if exc.log_traceback else None,
            )
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": "Request payload failed validation.",
                "details": {"errors": exc.errors()},
            },
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", extra={"path": request.url.path})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_error",
                "message": "An unexpected error occurred.",
            },
        )
