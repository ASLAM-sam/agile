"""Provider selection.

The one place that knows which concrete client backs `LLMProvider`. Services
depend on this function rather than on a class, so adding a provider is a new
module plus a branch here — the agent layer never learns there was a choice.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.protocol import LLMProvider

logger = get_logger(__name__)


def build_llm_provider() -> LLMProvider:
    """Construct the client for the configured provider.

    Imports are deferred so a missing optional SDK only matters to the provider
    that needs it: running on Gemini must not require the Anthropic package to
    be installed, or the reverse.
    """
    if settings.llm_provider == "gemini":
        from app.llm.gemini import GeminiClient

        return GeminiClient()

    from app.llm.client import LLMClient

    return LLMClient()
