"""Failure classification shared by every provider.

The provider manager has to decide, for each failure, between three actions:
try again, try someone else, or give up. That decision needs information only
the provider possesses — an HTTP status, an SDK exception type, a quota
message — so each adapter tags the errors it raises and the manager reads the
tag instead of parsing messages.

Message parsing was the alternative, and it is the wrong one: provider wording
changes without notice, and a routing decision that silently degrades when a
vendor rewrites an error string is worse than no routing at all.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.enums import ErrorKind
from app.core.exceptions import AegisError, LLMError

#: Attribute name used to carry the classification on an exception instance.
_KIND_ATTRIBUTE = "aegis_error_kind"
_CATEGORY_ATTRIBUTE = "aegis_error_category"


class LLMErrorCategory(StrEnum):
    """Structured error categories for provider-independent error classification."""

    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    RATE_LIMIT_RPM = "RATE_LIMIT_RPM"
    RATE_LIMIT_RPD = "RATE_LIMIT_RPD"
    RATE_LIMIT_TPM = "RATE_LIMIT_TPM"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    TIMEOUT = "TIMEOUT"
    SERVER_ERROR = "SERVER_ERROR"
    BAD_REQUEST = "BAD_REQUEST"
    INVALID_MODEL = "INVALID_MODEL"
    UNKNOWN = "UNKNOWN"

    @property
    def is_auth(self) -> bool:
        return self in (LLMErrorCategory.AUTHENTICATION, LLMErrorCategory.AUTHORIZATION)

    @property
    def is_rate_limit(self) -> bool:
        return self in (
            LLMErrorCategory.RATE_LIMIT_RPM,
            LLMErrorCategory.RATE_LIMIT_RPD,
            LLMErrorCategory.RATE_LIMIT_TPM,
            LLMErrorCategory.QUOTA_EXHAUSTED,
        )

    @property
    def is_retryable(self) -> bool:
        return self in (
            LLMErrorCategory.RATE_LIMIT_RPM,
            LLMErrorCategory.TIMEOUT,
            LLMErrorCategory.SERVER_ERROR,
        )

    def to_error_kind(self) -> ErrorKind:
        if self.is_auth:
            return ErrorKind.AUTH
        if self.is_rate_limit:
            return ErrorKind.QUOTA
        if self in (LLMErrorCategory.TIMEOUT, LLMErrorCategory.SERVER_ERROR):
            return ErrorKind.RETRYABLE
        if self is LLMErrorCategory.INVALID_MODEL:
            return ErrorKind.UNAVAILABLE
        return ErrorKind.FATAL


def classify_http_error(
    status_code: int,
    message: str = "",
    headers: dict[str, str] | None = None,
) -> LLMErrorCategory:
    """Classify an HTTP error status and message into an LLMErrorCategory."""
    msg_lower = (message or "").lower()

    if status_code in (401, 403):
        if "permission" in msg_lower or "unauthorized" in msg_lower or status_code == 403:
            return LLMErrorCategory.AUTHORIZATION
        return LLMErrorCategory.AUTHENTICATION

    if status_code == 429:
        if "tokens per minute" in msg_lower or "tpm" in msg_lower:
            return LLMErrorCategory.RATE_LIMIT_TPM
        if "requests per day" in msg_lower or "rpd" in msg_lower or "daily" in msg_lower:
            return LLMErrorCategory.RATE_LIMIT_RPD
        if "requests per minute" in msg_lower or "rpm" in msg_lower or "rate limit" in msg_lower:
            return LLMErrorCategory.RATE_LIMIT_RPM
        if "quota" in msg_lower or "exhausted" in msg_lower:
            return LLMErrorCategory.QUOTA_EXHAUSTED
        return LLMErrorCategory.RATE_LIMIT_RPM

    if status_code == 404:
        return LLMErrorCategory.INVALID_MODEL

    if status_code == 408:
        return LLMErrorCategory.TIMEOUT

    if status_code == 400:
        if any(term in msg_lower for term in ("model", "not found", "unknown model")):
            return LLMErrorCategory.INVALID_MODEL
        return LLMErrorCategory.BAD_REQUEST

    if 500 <= status_code < 600:
        if status_code in (504, 524) or "timeout" in msg_lower:
            return LLMErrorCategory.TIMEOUT
        return LLMErrorCategory.SERVER_ERROR

    if "timeout" in msg_lower:
        return LLMErrorCategory.TIMEOUT

    return LLMErrorCategory.UNKNOWN


def tag(
    error: AegisError,
    kind: ErrorKind | None = None,
    category: LLMErrorCategory | None = None,
) -> AegisError:
    """Attach failover and error classifications to an error and return it."""
    if category is not None:
        setattr(error, _CATEGORY_ATTRIBUTE, category)
        if kind is None:
            kind = category.to_error_kind()

    if kind is not None:
        setattr(error, _KIND_ATTRIBUTE, kind)
    return error


def category_of(error: BaseException) -> LLMErrorCategory:
    """Read the error category, returning UNKNOWN if untagged."""
    cat = getattr(error, _CATEGORY_ATTRIBUTE, None)
    if isinstance(cat, LLMErrorCategory):
        return cat
    # Fallback from ErrorKind if present
    kind = kind_of(error)
    if kind == ErrorKind.AUTH:
        return LLMErrorCategory.AUTHENTICATION
    if kind == ErrorKind.QUOTA:
        return LLMErrorCategory.RATE_LIMIT_RPM
    if kind == ErrorKind.RETRYABLE:
        return LLMErrorCategory.SERVER_ERROR
    if kind == ErrorKind.UNAVAILABLE:
        return LLMErrorCategory.INVALID_MODEL
    return LLMErrorCategory.UNKNOWN


def kind_of(error: BaseException) -> ErrorKind:
    """Read the classification, defaulting to the safe answer."""
    kind = getattr(error, _KIND_ATTRIBUTE, None)
    return kind if isinstance(kind, ErrorKind) else ErrorKind.FATAL


class AllProvidersFailed(LLMError):
    """Every eligible provider was tried and none produced a response.

    Carries the per-provider reasons so the message names what actually
    happened rather than reporting a generic outage.
    """

    error_code = "all_providers_failed"

    def __init__(self, attempts: dict[str, str], *, task: str = "") -> None:
        if attempts:
            summary = "; ".join(f"{name}: {reason}" for name, reason in attempts.items())
            message = f"Every configured model provider failed. {summary}"
        else:
            message = (
                "No model provider is available. Configure at least one provider key "
                "in backend/.env — see LLM_PROVIDER_PRIORITY for the order they are "
                "tried in."
            )
        super().__init__(message, details={"attempts": attempts, "task": task})
        self.attempts = attempts


class GeminiAllAccountsUnavailableError(AllProvidersFailed):
    """Every eligible Gemini account was tried and none produced a response.

    Carries the per-account reasons so the message identifies why each account failed.
    """

    error_code = "gemini_all_accounts_unavailable"

    def __init__(self, attempts: dict[str, str], *, agent: str = "") -> None:
        if attempts:
            summary = "; ".join(f"{name}: {reason}" for name, reason in attempts.items())
            msg = (
                f"All configured Gemini accounts are currently unavailable for agent '{agent}'."
                f" {summary}"
            )
        else:
            msg = f"No Gemini accounts available for agent '{agent}'."
        super().__init__(attempts, task=agent)
        self.message = msg

