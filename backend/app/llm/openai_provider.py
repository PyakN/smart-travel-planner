from typing import Any

import openai
from pydantic import BaseModel

from app.llm.base import LLMError, LLMResponse, TransientLLMError

RETRYABLE_ERRORS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
    openai.LengthFinishReasonError,
)


class OpenAIProvider:
    def __init__(self, api_key: str | None = None, client: Any = None) -> None:
        # `client` is injectable for tests; it must expose `responses.parse`.
        # The SDK's own retries are off: LLMService handles retries for every provider.
        self._client = client or openai.AsyncOpenAI(api_key=api_key, max_retries=0)

    async def generate[T: BaseModel](
        self, *, model: str, system: str, prompt: str, schema: type[T], max_output_tokens: int
    ) -> LLMResponse[T]:
        try:
            response = await self._client.responses.parse(
                model=model,
                instructions=system,
                input=prompt,
                text_format=schema,
                max_output_tokens=max_output_tokens,
            )
        except RETRYABLE_ERRORS as exc:
            raise TransientLLMError(f"OpenAI transient error: {type(exc).__name__}") from exc
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenAI rejected the request: {exc}") from exc

        parsed = response.output_parsed
        if not isinstance(parsed, schema):
            raise TransientLLMError("OpenAI returned no parsable output")
        usage = response.usage
        return LLMResponse(
            parsed=parsed,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
        )
