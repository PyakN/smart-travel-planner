import asyncio
import hashlib
import json
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel

from app.llm.base import (
    LLMBudgetExceededError,
    LLMProvider,
    LLMUnavailableError,
    TransientLLMError,
)

logger = logging.getLogger(__name__)


class TokenBudget:
    """Per-process daily token cap: a cheap guard against runaway spending."""

    def __init__(self, daily_limit: int, today: Callable[[], date] | None = None) -> None:
        self.daily_limit = daily_limit
        self._today = today or (lambda: datetime.now(UTC).date())
        self._day = self._today()
        self.used = 0

    def _roll_over(self) -> None:
        if (today := self._today()) != self._day:
            self._day, self.used = today, 0

    def check(self) -> None:
        self._roll_over()
        if self.used >= self.daily_limit:
            raise LLMBudgetExceededError(f"daily LLM token budget of {self.daily_limit} used up")

    def record(self, tokens: int) -> None:
        self._roll_over()
        self.used += tokens


class ResponseCache:
    """In-memory LRU of parsed responses, keyed by everything that affects the output."""

    def __init__(self, max_size: int) -> None:
        self.max_size = max_size
        self._items: OrderedDict[str, dict[str, Any]] = OrderedDict()

    @staticmethod
    def key(model: str, system: str, prompt: str, schema: type[BaseModel]) -> str:
        payload = json.dumps([model, system, prompt, schema.model_json_schema()], sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        if key not in self._items:
            return None
        self._items.move_to_end(key)
        return self._items[key]

    def put(self, key: str, value: dict[str, Any]) -> None:
        if self.max_size <= 0:
            return
        self._items[key] = value
        self._items.move_to_end(key)
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)


class LLMService:
    """Provider-agnostic structured generation with retries, fallback, timeout, cache, budget."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        model: str,
        fallback_model: str | None = None,
        timeout_s: float = 30.0,
        max_retries: int = 2,
        max_output_tokens: int = 2048,
        budget: TokenBudget | None = None,
        cache: ResponseCache | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.provider = provider
        self.models = [model] + ([fallback_model] if fallback_model else [])
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.max_output_tokens = max_output_tokens
        self.budget = budget or TokenBudget(daily_limit=1_000_000)
        self.cache = cache or ResponseCache(max_size=0)
        self._sleep = sleep

    async def generate[T: BaseModel](self, *, system: str, prompt: str, schema: type[T]) -> T:
        key = ResponseCache.key(self.models[0], system, prompt, schema)
        if (cached := self.cache.get(key)) is not None:
            return schema.model_validate(cached)

        self.budget.check()
        last_error: Exception | None = None
        for model in self.models:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await asyncio.wait_for(
                        self.provider.generate(
                            model=model,
                            system=system,
                            prompt=prompt,
                            schema=schema,
                            max_output_tokens=self.max_output_tokens,
                        ),
                        timeout=self.timeout_s,
                    )
                except (TransientLLMError, TimeoutError) as exc:
                    last_error = exc
                    logger.warning("LLM %s attempt %d failed: %r", model, attempt + 1, exc)
                    if attempt < self.max_retries:
                        await self._sleep(2**attempt)
                    continue
                self.budget.record(response.input_tokens + response.output_tokens)
                self.cache.put(key, response.parsed.model_dump(mode="json"))
                return response.parsed
        raise LLMUnavailableError(f"LLM failed after retries on {self.models}") from last_error
