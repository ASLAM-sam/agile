"""Model provider adapters.

One module per protocol, not one per vendor: `native` covers the two
first-party SDKs, `openai_compatible` covers every vendor speaking the OpenAI
chat-completions contract.
"""

from app.llm.providers.base import ProviderAdapter, ProviderSpec
from app.llm.providers.registry import (
    PROVIDER_FACTORIES,
    PROVIDER_LABELS,
    ProviderRegistry,
    build_providers,
)

__all__ = [
    "PROVIDER_FACTORIES",
    "PROVIDER_LABELS",
    "ProviderAdapter",
    "ProviderRegistry",
    "ProviderSpec",
    "build_providers",
]
