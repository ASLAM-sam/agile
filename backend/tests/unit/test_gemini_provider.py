"""The Gemini provider must be interchangeable with the Anthropic one.

Nothing here touches the network. The SDK's streaming call is replaced with a
scripted async iterator, so these tests assert what the client does with a
response rather than what Google returns for a prompt.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.core.exceptions import ConfigurationError, LLMError
from app.llm.factory import build_llm_provider
from app.llm.gemini import GeminiClient
from app.llm.manager import ProviderManager
from app.llm.protocol import LLMProvider
from app.llm.schema import array, obj, string
from app.llm.types import PromptBundle

SCHEMA = obj(
    {
        "name": string("Project name."),
        "features": array(string("A feature.")),
    }
)


def usage(prompt: int = 100, candidates: int = 40, thoughts: int = 0, cached: int = 0) -> Any:
    return genai_types.GenerateContentResponseUsageMetadata(
        prompt_token_count=prompt,
        candidates_token_count=candidates,
        thoughts_token_count=thoughts,
        cached_content_token_count=cached,
    )


def chunk(
    text: str | None = None,
    *,
    finish_reason: str | None = None,
    usage_metadata: Any = None,
    model_version: str = "gemini-2.5-flash",
) -> SimpleNamespace:
    """One streamed chunk, carrying only what the client reads off it."""
    candidates = []
    if finish_reason is not None:
        candidates.append(SimpleNamespace(finish_reason=SimpleNamespace(name=finish_reason)))
    return SimpleNamespace(
        text=text,
        model_version=model_version,
        usage_metadata=usage_metadata,
        candidates=candidates,
    )


@pytest.fixture(scope="module")
def client() -> GeminiClient:
    """A client with credentials that are never used.

    Module-scoped because constructing the SDK client costs over a second and
    every test that exercises the transport replaces it wholesale via
    `script()`. Building one per test added forty seconds to the suite.
    """
    return GeminiClient(api_key="test-key", model="gemini-2.5-flash", max_retries=0)


def script(client: GeminiClient, chunks: list[Any], captured: dict[str, Any] | None = None) -> None:
    """Make the next streamed call yield `chunks`."""

    async def fake_stream(**kwargs: Any) -> Any:
        if captured is not None:
            captured.update(kwargs)

        async def gen() -> Any:
            for item in chunks:
                yield item

        return gen()

    client._client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(
        generate_content_stream=fake_stream
    )))


class TestProviderSelection:
    """`LLM_PROVIDER` names the *preferred* provider, not the only one.

    The factory returns the shared `ProviderManager` rather than a concrete
    client: every configured provider stays reachable behind the preferred one,
    which is what lets a run continue when the preferred one hits its quota.
    """

    def test_gemini_client_satisfies_the_protocol(self, client: GeminiClient) -> None:
        assert isinstance(client, LLMProvider)

    def test_the_factory_returns_the_shared_manager(self) -> None:
        manager = build_llm_provider()
        assert isinstance(manager, ProviderManager)
        # Sharing is the point: cooldowns and the prompt cache are worthless
        # if a fresh manager is built per request.
        assert build_llm_provider() is manager

    def test_the_manager_satisfies_the_protocol_agents_depend_on(self) -> None:
        assert isinstance(build_llm_provider(), LLMProvider)

    @pytest.mark.parametrize(
        "preferred, key_attribute, key_value",
        [
            ("gemini", "google_api_key", "test-key"),
            ("anthropic", "anthropic_api_key", "sk-ant-test"),
            ("groq", "groq_api_key", "gsk-test"),
        ],
    )
    def test_the_preferred_provider_leads_the_routing_order(
        self,
        monkeypatch: pytest.MonkeyPatch,
        preferred: str,
        key_attribute: str,
        key_value: str,
    ) -> None:
        monkeypatch.setattr("app.core.config.settings.llm_provider", preferred)
        monkeypatch.setattr(f"app.core.config.settings.{key_attribute}", key_value)

        snapshot = build_llm_provider().stats_snapshot()
        assert snapshot["priority"][0] == preferred
        assert preferred in snapshot["available_providers"]

    def test_the_other_providers_remain_behind_the_preferred_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("app.core.config.settings.llm_provider", "gemini")
        monkeypatch.setattr("app.core.config.settings.google_api_key", "test-key")
        monkeypatch.setattr("app.core.config.settings.groq_api_key", "gsk-test")

        snapshot = build_llm_provider().stats_snapshot()
        assert snapshot["priority"][0] == "gemini"
        assert "groq" in snapshot["priority"], "a fallback must still be reachable"

    def test_a_missing_key_names_the_variable_and_where_to_get_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("app.core.config.settings.google_api_key", None)
        with pytest.raises(ConfigurationError) as exc:
            GeminiClient()
        assert "GOOGLE_API_KEY" in str(exc.value)
        assert "aistudio.google.com" in str(exc.value)


class TestStructuredOutput:
    """Schemas built by `llm/schema.py` must reach Gemini unmodified."""

    async def test_the_schema_is_passed_through_as_json_schema(
        self, client: GeminiClient
    ) -> None:
        captured: dict[str, Any] = {}
        script(client, [chunk('{"name":"x","features":[]}', finish_reason="STOP",
                              usage_metadata=usage())], captured)

        await client.complete_structured(
            PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
        )

        config = captured["config"]
        assert config.response_json_schema == SCHEMA
        assert config.response_mime_type == "application/json"
        # response_schema and response_json_schema are mutually exclusive.
        assert config.response_schema is None

    async def test_additional_properties_false_survives(self, client: GeminiClient) -> None:
        captured: dict[str, Any] = {}
        script(client, [chunk('{"name":"x","features":[]}', finish_reason="STOP",
                              usage_metadata=usage())], captured)
        await client.complete_structured(
            PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
        )
        assert captured["config"].response_json_schema["additionalProperties"] is False

    async def test_chunks_are_reassembled_into_one_object(self, client: GeminiClient) -> None:
        script(client, [
            chunk('{"name":"Port'),
            chunk('folio","features":["a"'),
            chunk(']}', finish_reason="STOP", usage_metadata=usage()),
        ])
        result = await client.complete_structured(
            PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
        )
        assert result.data == {"name": "Portfolio", "features": ["a"]}

    async def test_both_system_segments_are_sent(self, client: GeminiClient) -> None:
        captured: dict[str, Any] = {}
        script(client, [chunk('{"name":"x","features":[]}', finish_reason="STOP",
                              usage_metadata=usage())], captured)
        await client.complete_structured(
            PromptBundle(
                cacheable_system="STABLE PREFIX",
                volatile_system="PER RUN",
                user_message="u",
                schema=SCHEMA,
            )
        )
        instruction = captured["config"].system_instruction
        assert instruction.index("STABLE PREFIX") < instruction.index("PER RUN")

    async def test_a_schema_is_required(self, client: GeminiClient) -> None:
        with pytest.raises(ValueError, match="requires a schema"):
            await client.complete_structured(PromptBundle(cacheable_system="s", user_message="u"))


class TestFailureModes:
    """Each failure must say what happened, not just that something did."""

    async def test_truncation_is_reported_as_truncation(self, client: GeminiClient) -> None:
        script(client, [chunk('{"name":"x"', finish_reason="MAX_TOKENS", usage_metadata=usage())])
        with pytest.raises(LLMError, match="truncated"):
            await client.complete_structured(
                PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
            )

    @pytest.mark.parametrize("reason", ["SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "RECITATION"])
    async def test_refusals_are_distinguished_from_errors(
        self, client: GeminiClient, reason: str
    ) -> None:
        script(client, [chunk("", finish_reason=reason, usage_metadata=usage())])
        with pytest.raises(LLMError, match="declined"):
            await client.complete_text(PromptBundle(cacheable_system="s", user_message="u"))

    async def test_an_empty_structured_response_is_an_error(self, client: GeminiClient) -> None:
        script(client, [chunk("", finish_reason="STOP", usage_metadata=usage())])
        with pytest.raises(LLMError, match="empty response"):
            await client.complete_structured(
                PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
            )

    async def test_non_json_output_reports_a_preview(self, client: GeminiClient) -> None:
        script(client, [chunk("Sorry, I cannot.", finish_reason="STOP", usage_metadata=usage())])
        with pytest.raises(LLMError, match="not valid JSON"):
            await client.complete_structured(
                PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
            )

    async def test_a_json_array_is_rejected(self, client: GeminiClient) -> None:
        script(client, [chunk("[1,2]", finish_reason="STOP", usage_metadata=usage())])
        with pytest.raises(LLMError, match="must be a JSON object"):
            await client.complete_structured(
                PromptBundle(cacheable_system="s", user_message="u", schema=SCHEMA)
            )


class TestErrorTranslation:
    """Provider errors become the platform error that names the fix."""

    def error(self, code: int, message: str) -> genai_errors.APIError:
        return genai_errors.ClientError(code, {"error": {"message": message, "status": "X"}})

    def test_quota_exhaustion_explains_the_free_tier_limits(self, client: GeminiClient) -> None:
        translated = client._translate(
            self.error(429, "Quota exceeded for quota metric 'Generate requests'"),
            PromptBundle(cacheable_system="s"),
        )
        assert isinstance(translated, ConfigurationError)
        assert translated.status_code == 503
        assert "free tier" in translated.message
        assert "GENERATION_BATCH_SIZE" in translated.message

    @pytest.mark.parametrize("code", [401, 403])
    def test_a_rejected_key_points_at_ai_studio(self, client: GeminiClient, code: int) -> None:
        translated = client._translate(
            self.error(code, "API key not valid"), PromptBundle(cacheable_system="s")
        )
        assert isinstance(translated, ConfigurationError)
        assert "aistudio.google.com" in translated.message

    def test_an_unknown_model_names_the_setting(self, client: GeminiClient) -> None:
        translated = client._translate(
            self.error(404, "models/gemini-9 is not found for API version v1beta"),
            PromptBundle(cacheable_system="s"),
        )
        assert isinstance(translated, ConfigurationError)
        assert "GEMINI_MODEL" in translated.message

    def test_other_rejections_stay_llm_errors(self, client: GeminiClient) -> None:
        translated = client._translate(
            self.error(400, "Invalid value for max_output_tokens"),
            PromptBundle(cacheable_system="s", metadata={"agent": "analyst"}),
        )
        assert isinstance(translated, LLMError)
        assert translated.status_code == 502
        assert translated.details == {"agent": "analyst"}

    def test_the_raw_envelope_is_not_shown(self, client: GeminiClient) -> None:
        translated = client._translate(
            self.error(400, "Invalid value"), PromptBundle(cacheable_system="s")
        )
        assert "RESOURCE_EXHAUSTED" not in translated.message
        assert "{'error'" not in translated.message

    @pytest.mark.parametrize(
        "code, retryable",
        [(429, True), (500, True), (503, True), (400, False), (401, False), (404, False)],
    )
    def test_retryable_classification(
        self, client: GeminiClient, code: int, retryable: bool
    ) -> None:
        assert client._is_retryable(self.error(code, "m")) is retryable


class TestUsageAccounting:
    """Token counts feed the run report, so they must be complete."""

    async def test_counts_are_mapped(self, client: GeminiClient) -> None:
        script(client, [chunk("hello", finish_reason="STOP",
                              usage_metadata=usage(prompt=1200, candidates=300, cached=800))])
        result = await client.complete_text(PromptBundle(cacheable_system="s", user_message="u"))
        assert result.usage.input_tokens == 1200
        assert result.usage.cache_read_tokens == 800

    async def test_thinking_tokens_count_as_output(self, client: GeminiClient) -> None:
        # They are billed as output but reported separately; omitting them makes
        # a reasoning-heavy run look cheaper than it was.
        script(client, [chunk("hello", finish_reason="STOP",
                              usage_metadata=usage(candidates=300, thoughts=900))])
        result = await client.complete_text(PromptBundle(cacheable_system="s", user_message="u"))
        assert result.usage.output_tokens == 1200

    async def test_the_last_chunk_wins(self, client: GeminiClient) -> None:
        # Usage is cumulative and repeated on every chunk; summing double-counts.
        script(client, [
            chunk("a", usage_metadata=usage(prompt=10, candidates=1)),
            chunk("b", finish_reason="STOP", usage_metadata=usage(prompt=10, candidates=2)),
        ])
        result = await client.complete_text(PromptBundle(cacheable_system="s", user_message="u"))
        assert result.usage.input_tokens == 10
        assert result.usage.output_tokens == 2
