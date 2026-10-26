from typing import Any

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.llm.base import LLMError, LLMResponse, TransientLLMError

RETRYABLE_CLIENT_CODES = {408, 429}


class GeminiProvider:
    def __init__(self, api_key: str | None = None, client: Any = None) -> None:
        # `client` is injectable for tests; it must expose `aio.models.generate_content`.
        self._client = client or genai.Client(api_key=api_key)

    async def generate[T: BaseModel](
        self, *, model: str, system: str, prompt: str, schema: type[T], max_output_tokens: int
    ) -> LLMResponse[T]:
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.2,
            max_output_tokens=max_output_tokens,
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=model, contents=prompt, config=config
            )
        except errors.ServerError as exc:
            raise TransientLLMError(f"Gemini server error {exc.code}") from exc
        except errors.ClientError as exc:
            if exc.code in RETRYABLE_CLIENT_CODES:
                raise TransientLLMError(f"Gemini rate limited ({exc.code})") from exc
            raise LLMError(f"Gemini rejected the request ({exc.code}): {exc.message}") from exc
        except httpx.TransportError as exc:
            raise TransientLLMError(f"Gemini transport error: {exc!r}") from exc

        parsed = response.parsed
        if not isinstance(parsed, schema):
            try:
                parsed = schema.model_validate_json(response.text or "")
            except ValidationError as exc:
                raise TransientLLMError("Gemini returned output that fails the schema") from exc

        usage = response.usage_metadata
        return LLMResponse(
            parsed=parsed,
            input_tokens=(usage and usage.prompt_token_count) or 0,
            output_tokens=((usage and usage.candidates_token_count) or 0)
            + ((usage and usage.thoughts_token_count) or 0),
        )
