"""Providers are tested against stubbed SDK clients; no network calls."""

import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest
from google.genai import errors
from pydantic import BaseModel, SecretStr

from app.config import Settings
from app.llm.base import LLMError, LLMProvider, TransientLLMError
from app.llm.factory import create_llm_service
from app.llm.gemini_provider import GeminiProvider
from app.llm.openai_provider import OpenAIProvider


class Answer(BaseModel):
    value: int


class Stub:
    """Async callable that returns or raises `outcome` and records its kwargs."""

    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.kwargs: dict[str, Any] = {}

    async def __call__(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(outcome := self.outcome, Exception):
            raise outcome
        return outcome


def run(provider: LLMProvider) -> Any:
    return asyncio.run(
        provider.generate(model="m", system="sys", prompt="p", schema=Answer, max_output_tokens=64)
    )


def gemini(outcome: Any) -> tuple[GeminiProvider, Stub]:
    stub = Stub(outcome)
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=stub)))
    return GeminiProvider(client=client), stub


def gemini_response(parsed: Any, text: str = "") -> SimpleNamespace:
    usage = SimpleNamespace(prompt_token_count=10, candidates_token_count=5, thoughts_token_count=3)
    return SimpleNamespace(parsed=parsed, text=text, usage_metadata=usage)


class TestGemini:
    def test_success_counts_thinking_tokens(self) -> None:
        provider, stub = gemini(gemini_response(Answer(value=1)))
        response = run(provider)
        assert response.parsed == Answer(value=1)
        assert (response.input_tokens, response.output_tokens) == (10, 8)
        assert stub.kwargs["config"].system_instruction == "sys"
        assert stub.kwargs["config"].response_schema is Answer

    def test_falls_back_to_parsing_text(self) -> None:
        provider, _ = gemini(gemini_response(None, text='{"value": 7}'))
        assert run(provider).parsed == Answer(value=7)

    def test_invalid_output_is_transient(self) -> None:
        provider, _ = gemini(gemini_response(None, text="not json"))
        with pytest.raises(TransientLLMError):
            run(provider)

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (errors.ServerError(503, {"error": {"message": "overloaded"}}), TransientLLMError),
            (errors.ClientError(429, {"error": {"message": "quota"}}), TransientLLMError),
            (httpx.ConnectTimeout("slow"), TransientLLMError),
        ],
    )
    def test_retryable_errors(self, error: Exception, expected: type[Exception]) -> None:
        provider, _ = gemini(error)
        with pytest.raises(expected):
            run(provider)

    def test_bad_request_is_permanent(self) -> None:
        provider, _ = gemini(errors.ClientError(400, {"error": {"message": "bad"}}))
        with pytest.raises(LLMError) as info:
            run(provider)
        assert not isinstance(info.value, TransientLLMError)


def openai_provider(outcome: Any) -> OpenAIProvider:
    return OpenAIProvider(client=SimpleNamespace(responses=SimpleNamespace(parse=Stub(outcome))))


REQUEST = httpx.Request("POST", "https://api.openai.com/v1/responses")


class TestOpenAI:
    def test_success(self) -> None:
        usage = SimpleNamespace(input_tokens=12, output_tokens=4)
        response = run(openai_provider(SimpleNamespace(output_parsed=Answer(value=2), usage=usage)))
        assert (response.parsed.value, response.input_tokens, response.output_tokens) == (2, 12, 4)

    def test_rate_limit_is_transient(self) -> None:
        error = openai.RateLimitError(
            "slow down", response=httpx.Response(429, request=REQUEST), body=None
        )
        with pytest.raises(TransientLLMError):
            run(openai_provider(error))

    def test_auth_error_is_permanent(self) -> None:
        error = openai.AuthenticationError(
            "bad key", response=httpx.Response(401, request=REQUEST), body=None
        )
        with pytest.raises(LLMError) as info:
            run(openai_provider(error))
        assert not isinstance(info.value, TransientLLMError)

    def test_missing_output_is_transient(self) -> None:
        with pytest.raises(TransientLLMError):
            run(openai_provider(SimpleNamespace(output_parsed=None, usage=None)))


def isolated_settings(**overrides: Any) -> Settings:
    # Ignore the developer's .env so local LLM_* values can't change the outcome.
    return Settings(_env_file=None, database_url="postgresql://x", **overrides)


class TestFactory:
    def test_requires_api_key(self) -> None:
        settings = isolated_settings(llm_provider="gemini", gemini_api_key=None)
        with pytest.raises(LLMError, match="GEMINI_API_KEY"):
            create_llm_service(settings)

    def test_default_models(self) -> None:
        settings = isolated_settings(llm_provider="gemini", gemini_api_key=SecretStr("test-key"))
        service = create_llm_service(settings)
        assert service.models == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]

    def test_fallback_model_from_settings(self) -> None:
        settings = isolated_settings(
            llm_provider="gemini",
            gemini_api_key=SecretStr("test-key"),
            llm_fallback_model="gemini-3.6-flash",
        )
        service = create_llm_service(settings)
        assert service.models == ["gemini-3.5-flash-lite", "gemini-3.6-flash"]

    def test_no_fallback_to_the_model_itself(self) -> None:
        settings = isolated_settings(
            llm_provider="gemini",
            gemini_api_key=SecretStr("test-key"),
            llm_model="gemini-3.1-flash-lite",
        )
        assert create_llm_service(settings).models == ["gemini-3.1-flash-lite"]

    def test_no_default_fallback_for_openai(self) -> None:
        settings = isolated_settings(llm_provider="openai", openai_api_key=SecretStr("test-key"))
        assert create_llm_service(settings).models == ["gpt-5-mini"]
