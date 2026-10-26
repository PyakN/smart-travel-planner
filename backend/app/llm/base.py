from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


class LLMError(Exception):
    """Non-retryable LLM failure (bad request, auth, misconfiguration)."""


class TransientLLMError(LLMError):
    """Retryable failure: rate limit, server error, malformed structured output."""


class LLMUnavailableError(LLMError):
    """All retries and fallbacks failed."""


class LLMBudgetExceededError(LLMError):
    """The daily token budget is used up."""


@dataclass(frozen=True)
class LLMResponse[T: BaseModel]:
    parsed: T
    input_tokens: int
    output_tokens: int


class LLMProvider(Protocol):
    """One vendor API. Retries, caching and budgets live in LLMService, not here."""

    async def generate[T: BaseModel](
        self, *, model: str, system: str, prompt: str, schema: type[T], max_output_tokens: int
    ) -> LLMResponse[T]: ...
