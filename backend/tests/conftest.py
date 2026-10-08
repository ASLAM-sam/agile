"""Shared test fixtures.

The database is an in-memory SQLite instance per test, and the language model
is a deterministic double. Both keep the suite fast and hermetic: no test
touches the network, and no test depends on another's state.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio

# Environment must be configured before app.core.config is first imported.
#
# The empty AEGIS_ENV_FILE disables the dotenv source, so a developer's real
# backend/.env cannot reach the suite. Without it a stray ANTHROPIC_API_KEY or
# GENERATION_BATCH_SIZE on one machine silently changes what the tests exercise.
os.environ["AEGIS_ENV_FILE"] = ""
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use-only")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("AEGIS_MOCK_VALIDATION", "true")

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.adapters.registry import build_default_registry
from app.agents.registry import AgentRegistry
from app.db.base import Base
from app.db.session import get_session
from app.llm.factory import reset_llm_provider
from app.llm.types import Completion, PromptBundle, TextCompletion, TokenUsage
from app.main import create_app
from app.models import User as User  # Re-exported so the ORM registers metadata.
from app.workflow.memory import SharedProjectMemory


@pytest.fixture(autouse=True)
def _isolate_provider_manager():
    """Rebuild the shared provider manager for every test.

    The manager is a process-wide singleton in production, which is correct:
    cooldowns and the prompt cache have to outlive a run. In a test suite that
    same lifetime leaks — one test's monkeypatched settings, cooled-down
    provider or cached response would silently decide the next test's result.
    """
    reset_llm_provider()
    yield
    reset_llm_provider()


@pytest_asyncio.fixture
async def engine():
    """In-memory database, isolated per test.

    `StaticPool` keeps every connection pointed at the same in-memory database;
    without it each connection would get its own empty one.
    """
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as test_session:
        yield test_session


@pytest_asyncio.fixture
async def client(engine) -> AsyncIterator[AsyncClient]:
    """HTTP client bound to the app with the test database injected."""
    app = create_app()
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as test_session:
            try:
                yield test_session
                await test_session.commit()
            except Exception:
                await test_session.rollback()
                raise

    app.dependency_overrides[get_session] = override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def authed_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    """Client with a registered, signed-in user."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "engineer@aegisai.dev",
            "full_name": "Test Engineer",
            "password": "Str0ngPassphrase!",
        },
    )
    assert response.status_code == 201, response.text
    token = response.json()["tokens"]["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    yield client


@pytest.fixture
def adapters():
    return build_default_registry()


@pytest.fixture
def memory() -> SharedProjectMemory:
    return SharedProjectMemory(
        run_id="testrun",
        project_id="testproject",
        project_name="Test Project",
        project_slug="test-project",
        idea="A hospital management system for appointments and patient records",
    )


class StubLLM:
    """Deterministic language-model double.

    Returns queued responses in order. Used only in tests — the production
    code path always talks to the real provider through `LLMClient`.
    """

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self._responses = list(responses or [])
        self.calls: list[PromptBundle] = []

    @property
    def model(self) -> str:
        return "stub-model"

    def queue(self, payload: dict[str, Any]) -> None:
        self._responses.append(payload)

    async def complete_structured(self, prompt: PromptBundle) -> Completion:
        self.calls.append(prompt)
        if not self._responses:
            raise AssertionError(
                "StubLLM received an unexpected call; no response was queued."
            )
        return Completion(
            data=self._responses.pop(0),
            usage=TokenUsage(input_tokens=100, output_tokens=200),
            stop_reason="end_turn",
            model="stub-model",
        )

    async def complete_text(self, prompt: PromptBundle) -> TextCompletion:
        self.calls.append(prompt)
        return TextCompletion(
            text="stub response",
            usage=TokenUsage(input_tokens=10, output_tokens=20),
            model="stub-model",
        )

    async def aclose(self) -> None:
        return None


@pytest.fixture
def stub_llm() -> StubLLM:
    return StubLLM()


@pytest.fixture
def full_analysis_payload() -> dict[str, Any]:
    """A complete Business Analyst response for a full-stack project."""
    return {
        "executive_summary": "A hospital management system for appointments and records.",
        "project_overview": "Staff book appointments and manage patient records.",
        "scope_in": ["Appointment booking", "Patient records", "Staff management"],
        "scope_out": ["Billing", "Insurance claims"],
        "actors": ["Receptionist", "Doctor", "Administrator"],
        "entities": ["Patient", "Appointment", "Doctor", "Department"],
        "functional_requirements": [
            {
                "id": f"FR-{index:02d}",
                "title": f"Requirement {index}",
                "description": f"The system shall support capability {index}.",
                "priority": "must",
                "module": "Appointments",
            }
            for index in range(1, 10)
        ],
        "non_functional_requirements": [
            {
                "id": f"NFR-{index:02d}",
                "category": "performance",
                "requirement": f"Response within {index * 100} ms.",
            }
            for index in range(1, 6)
        ],
        "user_stories": [
            {
                "id": f"US-{index:02d}",
                "story": f"As a receptionist, I want feature {index}, so that I save time.",
                "acceptance_criteria": ["Given X, when Y, then Z"],
            }
            for index in range(1, 7)
        ],
        "use_cases": [
            {
                "id": f"UC-{index:02d}",
                "name": f"Use case {index}",
                "actor": "Receptionist",
                "main_flow": ["Step one", "Step two"],
                "alternate_flow": "",
            }
            for index in range(1, 5)
        ],
        "assumptions": ["Single hospital site"],
        "clarifications": [],
        "capabilities": {
            "needs_authentication": True,
            "needs_database": True,
            "needs_api": True,
            "needs_backend": True,
            "needs_frontend": True,
        },
        "complexity": "advanced",
        "rationale": "Staff roles differ and records must persist between sessions.",
    }


@pytest.fixture
def static_site_analysis_payload(full_analysis_payload: dict[str, Any]) -> dict[str, Any]:
    """A Business Analyst response for a frontend-only project."""
    payload = dict(full_analysis_payload)
    payload["executive_summary"] = "A personal portfolio website."
    payload["entities"] = []
    payload["capabilities"] = {
        "needs_authentication": False,
        "needs_database": False,
        "needs_api": False,
        "needs_backend": False,
        "needs_frontend": True,
    }
    payload["complexity"] = "minimal"
    payload["rationale"] = "Static content with no accounts and nothing to persist."
    return payload


@pytest.fixture
def agent_registry() -> AgentRegistry:
    return AgentRegistry()
