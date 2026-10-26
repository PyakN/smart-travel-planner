import asyncio
from datetime import date

import pytest
from pydantic import BaseModel

from app.llm.base import (
    LLMBudgetExceededError,
    LLMError,
    LLMUnavailableError,
    TransientLLMError,
)
from app.llm.service import LLMService, ResponseCache, TokenBudget
from tests.fakes import FakeProvider


class Answer(BaseModel):
    value: int


async def no_sleep(_: float) -> None:
    return None


def make_service(provider: FakeProvider, **kwargs: object) -> LLMService:
    return LLMService(provider, model="main", sleep=no_sleep, **kwargs)  # type: ignore[arg-type]


def generate(service: LLMService, prompt: str = "q") -> Answer:
    return asyncio.run(service.generate(system="s", prompt=prompt, schema=Answer))


def test_returns_parsed_response() -> None:
    assert generate(make_service(FakeProvider().queue(Answer(value=1)))) == Answer(value=1)


def test_retries_transient_errors() -> None:
    provider = FakeProvider().queue(TransientLLMError("503"), TransientLLMError("429"))
    provider.queue(Answer(value=2))
    assert generate(make_service(provider, max_retries=2)).value == 2
    assert len(provider.calls) == 3


def test_falls_back_to_second_model() -> None:
    provider = FakeProvider().queue(TransientLLMError("503"), TransientLLMError("503"))
    provider.queue(Answer(value=3))
    service = make_service(provider, max_retries=1, fallback_model="backup")
    assert generate(service).value == 3
    assert [c["model"] for c in provider.calls] == ["main", "main", "backup"]


def test_gives_up_after_all_attempts() -> None:
    provider = FakeProvider().queue(*[TransientLLMError("503")] * 3)
    with pytest.raises(LLMUnavailableError):
        generate(make_service(provider, max_retries=2))


def test_does_not_retry_permanent_errors() -> None:
    provider = FakeProvider().queue(LLMError("bad api key"))
    with pytest.raises(LLMError, match="bad api key"):
        generate(make_service(provider))
    assert len(provider.calls) == 1


def test_timeout_counts_as_transient() -> None:
    class SlowProvider(FakeProvider):
        async def generate(self, **kwargs):  # type: ignore[no-untyped-def,override]
            if not self.calls:
                self.calls.append(kwargs)
                await asyncio.sleep(1)
            return await super().generate(**kwargs)

    provider = SlowProvider().queue(Answer(value=4))
    assert generate(make_service(provider, timeout_s=0.01)).value == 4


def test_cache_avoids_second_call() -> None:
    provider = FakeProvider().queue(Answer(value=5))
    service = make_service(provider, cache=ResponseCache(max_size=10))
    assert generate(service) == generate(service) == Answer(value=5)
    assert len(provider.calls) == 1


def test_cache_evicts_least_recently_used() -> None:
    cache = ResponseCache(max_size=2)
    cache.put("a", {"v": 1})
    cache.put("b", {"v": 2})
    cache.get("a")
    cache.put("c", {"v": 3})
    assert cache.get("b") is None
    assert cache.get("a") == {"v": 1}


def test_budget_blocks_calls_when_used_up() -> None:
    provider = FakeProvider().queue(Answer(value=1), Answer(value=2))
    service = make_service(provider, budget=TokenBudget(daily_limit=100))
    generate(service, "first")  # uses 120 tokens
    with pytest.raises(LLMBudgetExceededError):
        generate(service, "second")


def test_budget_resets_next_day() -> None:
    days = iter([date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 2)])
    budget = TokenBudget(daily_limit=10, today=lambda: next(days))
    budget.record(50)
    budget.check()  # new day: no exception
    assert budget.used == 0
