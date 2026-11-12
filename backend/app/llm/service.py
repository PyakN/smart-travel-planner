import asyncio
import hashlib
import json
import logging
import time
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


class CircuitBreaker:
    """Stops calling an LLM that keeps failing. After `threshold` calls in a row that gave
    up (every retry of every model failed), calls fail at once for `cooldown_s`: during an
    outage, requests get their answer without waiting out the retries. Then calls go
    through again; a success closes the circuit, the next failure opens it again."""

    def __init__(
        self,
        threshold: int = 3,
        cooldown_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.threshold = threshold
        self.cooldown_s = cooldown_s
        self.clock = clock
        self.failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None and self.clock() < self._opened_at + self.cooldown_s

    def check(self) -> None:
        if self.is_open:
            raise LLMUnavailableError("the LLM failed repeatedly: not calling it for a while")

    def failed(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            logger.error(
                "LLM failed %d times in a row: not calling it for %.0f s",
                self.failures,
                self.cooldown_s,
            )
            self._opened_at = self.clock()

    def succeeded(self) -> None:
        if self._opened_at is not None:
            logger.info("LLM answers again")
        self.failures = 0
        self._opened_at = None


class LLMService:
    """Provider-agnostic structured generation with retries, fallback, timeout, cache, budget
    and a circuit breaker. One call takes at most `deadline_s`, retries included."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        model: str,
        fallback_model: str | None = None,
        timeout_s: float = 30.0,
        deadline_s: float = 40.0,
        max_retries: int = 2,
        max_output_tokens: int = 2048,
        budget: TokenBudget | None = None,
        cache: ResponseCache | None = None,
        circuit: CircuitBreaker | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.provider = provider
        self.models = [model] + ([fallback_model] if fallback_model else [])
        self.timeout_s = timeout_s
        self.deadline_s = deadline_s
        self.max_retries = max_retries
        self.max_output_tokens = max_output_tokens
        self.budget = budget or TokenBudget(daily_limit=1_000_000)
        self.cache = cache or ResponseCache(max_size=0)
        self.circuit = circuit or CircuitBreaker()
        self._sleep = sleep

    async def generate[T: BaseModel](self, *, system: str, prompt: str, schema: type[T]) -> T:
        key = ResponseCache.key(self.models[0], system, prompt, schema)
        if (cached := self.cache.get(key)) is not None:
            logger.info("LLM answer from the cache", extra={"schema": schema.__name__})
            return schema.model_validate(cached)

        self.circuit.check()
        self.budget.check()
        clock = asyncio.get_running_loop().time
        deadline = clock() + self.deadline_s
        last_error: Exception | None = None
        # Rounds of one try per model, with a pause between rounds: an overloaded model
        # (503s for minutes at a time) hands over to the next one at once.
        attempts = [(m, a) for a in range(self.max_retries + 1) for m in self.models]
        for model, attempt in attempts:
            if (left := deadline - clock()) <= 0:
                break
            started = time.perf_counter()
            try:
                response = await asyncio.wait_for(
                    self.provider.generate(
                        model=model,
                        system=system,
                        prompt=prompt,
                        schema=schema,
                        max_output_tokens=self.max_output_tokens,
                    ),
                    timeout=min(self.timeout_s, left),
                )
            except (TransientLLMError, TimeoutError) as exc:
                last_error = exc
                logger.warning("LLM %s attempt %d failed: %r", model, attempt + 1, exc)
                if model == self.models[-1] and attempt < self.max_retries:
                    if clock() + 2**attempt >= deadline:  # no time left to try again
                        break
                    await self._sleep(2**attempt)
                continue
            self.circuit.succeeded()
            self.budget.record(response.input_tokens + response.output_tokens)
            logger.info(
                "LLM answered",
                extra={
                    "schema": schema.__name__,
                    "model": model,
                    "attempt": attempt + 1,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                },
            )
            self.cache.put(key, response.parsed.model_dump(mode="json"))
            return response.parsed
        self.circuit.failed()
        raise LLMUnavailableError(f"LLM failed after retries on {self.models}") from last_error
