"""Language-model integration layer."""

from app.llm.factory import build_llm_provider
from app.llm.protocol import LLMProvider
from app.llm.types import Completion, PromptBundle, TextCompletion, TokenUsage

# The concrete clients are deliberately not re-exported here: importing this
# package must not drag in a provider SDK that the configured provider does
# not need. Import `app.llm.client` or `app.llm.gemini` directly if you need
# the class itself.
__all__ = [
    "Completion",
    "LLMProvider",
    "PromptBundle",
    "TextCompletion",
    "TokenUsage",
    "build_llm_provider",
]
