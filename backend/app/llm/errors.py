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

from app.core.enums import ErrorKind
from app.core.exceptions import AegisError, LLMError

#: Attribute name used to carry the classification on an exception instance.
_KIND_ATTRIBUTE = "aegis_error_kind"


def tag(error: AegisError, kind: ErrorKind) -> AegisError:
    """Attach a failover classification to an error and return it.

    Returns the error so call sites can `raise tag(SomeError(...), kind)`.
    """
    setattr(error, _KIND_ATTRIBUTE, kind)
    return error


def kind_of(error: BaseException) -> ErrorKind:
    """Read the classification, defaulting to the safe answer.

    An untagged error is treated as `FATAL`. That is deliberate: an unknown
    failure repeated across five providers costs five quotas and still fails,
    whereas failing fast surfaces the bug. Adapters tag everything they expect;
    anything untagged is by definition unexpected.
    """
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
