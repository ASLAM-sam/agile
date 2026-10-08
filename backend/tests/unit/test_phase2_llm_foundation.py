"""Unit tests for Phase 2 LLM Foundation.

Tests:
- CredentialManager & slot abstractions
- Safe credential masking
- Backup slot fallback & ignoring empty slots
- ModelRouter decoupled provider/model mapping
- LLMErrorCategory classification
- ProviderRegistry & adapters (Gemini, OpenAI, Mistral, GitHub Models, Groq)
- HTMLCssJsAdapter frontend foundation
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.adapters.base import ScaffoldContext
from app.adapters.frontend.html_css_js import HTMLCssJsAdapter
from app.core.config import Settings
from app.llm.credentials import CredentialManager, mask_key
from app.llm.errors import LLMErrorCategory, classify_http_error
from app.llm.providers.base import ProviderAdapter
from app.llm.providers.gemini import GeminiAdapter
from app.llm.providers.github_models import GitHubModelsAdapter
from app.llm.providers.groq import GroqAdapter
from app.llm.providers.mistral import MistralAdapter
from app.llm.providers.openai import OpenAIAdapter
from app.llm.providers.registry import ProviderRegistry
from app.llm.router import ModelRouter, RouteDecision


class DummySchema(BaseModel):
    name: str
    count: int


# =====================================================================
# 1. Safe Credential Masking & Management
# =====================================================================

def test_mask_key():
    assert mask_key(None) == "<unconfigured>"
    assert mask_key("") == "<unconfigured>"
    assert mask_key("short") == "****rt"
    assert mask_key("AIzaSyD-1234567890abcdef") == "****CDEF"
    assert "1234567890" not in mask_key("AIzaSyD-1234567890abcdef")


def test_credential_manager_empty_slots_ignored():
    cfg = Settings(
        frontend_api_key01="front-secret-key-1234",
        backend_api_key01=None,
        database_api_key01="",
    )
    cm = CredentialManager.from_settings(cfg)

    # Empty slots are ignored
    slots = cm.list_slots()
    slot_names = [s.name for s in slots]
    assert "FRONTEND_API_KEY01" in slot_names
    assert "BACKEND_API_KEY01" not in slot_names
    assert "DATABASE_API_KEY01" not in slot_names

    # Masked values
    front_slot = next(s for s in slots if s.name == "FRONTEND_API_KEY01")
    assert front_slot.masked_key == "****1234"
    assert "secret" not in front_slot.masked_key


def test_credential_manager_fallback():
    cfg = Settings(
        frontend_api_key01="front-key",
    )
    cm = CredentialManager.from_settings(cfg)

    primary = cm.get_primary("FRONTEND_API_KEY01")
    assert primary is not None
    assert primary.key == "front-key"

    # When primary is cooling down, availability reports false
    cm.mark_rate_limited("FRONTEND_API_KEY01", cooldown_seconds=60)
    assert not cm.is_available("FRONTEND_API_KEY01")


# =====================================================================
# 2. Model Router Decoupling
# =====================================================================

def test_model_router_decoupled_routing():
    cfg = Settings(default_provider="openai")
    router = ModelRouter(settings=cfg)

    decision = router.route(agent_role="frontend_engineer", task_kind=None)
    assert isinstance(decision, RouteDecision)
    assert decision.provider == "openai"
    assert "gpt" in decision.model
    assert decision.credential_slot == "FRONTEND_API_KEY01"
    assert "gemini" in decision.fallback_providers


def test_model_router_mistral_selection():
    cfg = Settings(default_provider="mistral", mistral_model="codestral-latest")
    router = ModelRouter(settings=cfg)

    decision = router.route(agent_role="backend_engineer")
    assert decision.provider == "mistral"
    assert decision.model == "codestral-latest"
    assert decision.credential_slot == "BACKEND_API_KEY01"


# =====================================================================
# 3. LLM Error Category Classification
# =====================================================================

def test_classify_http_error():
    assert classify_http_error(401) == LLMErrorCategory.AUTHENTICATION
    assert classify_http_error(403) == LLMErrorCategory.AUTHORIZATION
    assert classify_http_error(404) == LLMErrorCategory.INVALID_MODEL
    assert classify_http_error(408) == LLMErrorCategory.TIMEOUT
    assert classify_http_error(429, "tpm limit exceeded") == LLMErrorCategory.RATE_LIMIT_TPM
    assert classify_http_error(429, "daily request quota exhausted") == LLMErrorCategory.RATE_LIMIT_RPD
    assert classify_http_error(429, "rate limit exceeded") == LLMErrorCategory.RATE_LIMIT_RPM
    assert classify_http_error(500) == LLMErrorCategory.SERVER_ERROR
    assert classify_http_error(503) == LLMErrorCategory.SERVER_ERROR
    assert classify_http_error(400) == LLMErrorCategory.BAD_REQUEST


# =====================================================================
# 4. Provider Registry & Adapters
# =====================================================================

def test_provider_registry_adapters():
    cfg = Settings(
        frontend_api_key01="mock-google-key",
        openai_api_key="mock-openai-key",
        mistral_api_key="mock-mistral-key",
        github_models_token="mock-gh-token",
        groq_api_key="mock-groq-key",
    )
    registry = ProviderRegistry(settings=cfg)

    providers = registry.build_providers()
    assert "gemini" in providers
    assert "openai" in providers
    assert "mistral" in providers
    assert "github_models" in providers
    assert "groq" in providers

    assert isinstance(providers["gemini"], GeminiAdapter)
    assert isinstance(providers["openai"], OpenAIAdapter)
    assert isinstance(providers["mistral"], MistralAdapter)
    assert isinstance(providers["github_models"], GitHubModelsAdapter)
    assert isinstance(providers["groq"], GroqAdapter)

    for p in providers.values():
        assert isinstance(p, ProviderAdapter)
        assert hasattr(p, "complete_text")
        assert hasattr(p, "complete_structured")


# =====================================================================
# 5. HTML/CSS/JS Frontend Foundation
# =====================================================================

def test_html_css_js_adapter():
    adapter = HTMLCssJsAdapter()
    assert adapter.key == "html_css_js"
    assert "HTML" in adapter.display_name

    ctx = ScaffoldContext(
        project_name="Demo App",
        project_slug="demo-app",
        description="A simple demo",
    )

    scaffold_files = adapter.scaffold(ctx)
    paths = [f.path for f in scaffold_files]
    assert "frontend/index.html" in paths
    assert "frontend/css/styles.css" in paths
    assert "frontend/js/app.js" in paths

    dockerfile = adapter.dockerfile(ctx)
    assert "nginx:1.27-alpine" in dockerfile

    compose = adapter.compose_service(ctx)
    assert "build" in compose
