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
from app.llm.service import CircuitBreaker, LLMService, ResponseCache, TokenBudget
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


def test_falls_back_to_second_model_at_once() -> None:
    provider = FakeProvider().queue(TransientLLMError("503"), Answer(value=3))
    pauses: list[float] = []

    async def sleep(seconds: float) -> None:
        pauses.append(seconds)

    service = LLMService(provider, model="main", fallback_model="backup", sleep=sleep)
    assert generate(service).value == 3
    assert [c["model"] for c in provider.calls] == ["main", "backup"]
    assert pauses == []


def test_retries_alternate_between_the_models() -> None:
    provider = FakeProvider().queue(*[TransientLLMError("503")] * 3, Answer(value=3))
    pauses: list[float] = []

    async def sleep(seconds: float) -> None:
        pauses.append(seconds)

    service = LLMService(provider, model="main", fallback_model="backup", sleep=sleep)
    assert generate(service).value == 3
    assert [c["model"] for c in provider.calls] == ["main", "backup", "main", "backup"]
    assert pauses == [1]  # one pause, between the rounds


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


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_circuit_opens_after_calls_in_a_row_fail() -> None:
    provider = FakeProvider().queue(*[TransientLLMError("503")] * 2)
    clock = Clock()
    circuit = CircuitBreaker(threshold=2, cooldown_s=60, clock=clock)
    service = make_service(provider, max_retries=0, circuit=circuit)
    for prompt in ("a", "b"):
        with pytest.raises(LLMUnavailableError):
            generate(service, prompt)
    with pytest.raises(LLMUnavailableError, match="not calling it"):
        generate(service, "c")
    assert len(provider.calls) == 2  # the third call never reached the provider
    assert circuit.is_open

    clock.now += 60  # cooled down: calls go through, and a success closes it
    provider.queue(Answer(value=6))
    assert generate(service, "d").value == 6
    assert not circuit.is_open
    assert circuit.failures == 0


def test_circuit_opens_again_on_the_first_failure_after_the_cooldown() -> None:
    provider = FakeProvider().queue(*[TransientLLMError("503")] * 2)
    clock = Clock()
    circuit = CircuitBreaker(threshold=1, cooldown_s=60, clock=clock)
    service = make_service(provider, max_retries=0, circuit=circuit)
    with pytest.raises(LLMUnavailableError):
        generate(service, "a")
    clock.now += 60
    with pytest.raises(LLMUnavailableError):
        generate(service, "b")
    assert circuit.is_open


def test_a_success_resets_the_failures() -> None:
    provider = FakeProvider().queue(TransientLLMError("503"), Answer(value=7))
    provider.queue(TransientLLMError("503"))
    circuit = CircuitBreaker(threshold=2)
    service = make_service(provider, max_retries=0, circuit=circuit)
    with pytest.raises(LLMUnavailableError):
        generate(service, "a")
    generate(service, "b")
    with pytest.raises(LLMUnavailableError):
        generate(service, "c")
    assert not circuit.is_open


def test_permanent_errors_leave_the_circuit_closed() -> None:
    provider = FakeProvider().queue(LLMError("blocked"), LLMError("blocked"))
    circuit = CircuitBreaker(threshold=1)
    service = make_service(provider, circuit=circuit)
    for prompt in ("a", "b"):
        with pytest.raises(LLMError):
            generate(service, prompt)
    assert not circuit.is_open


class HangingProvider(FakeProvider):
    async def generate(self, **kwargs):  # type: ignore[no-untyped-def,override]
        self.calls.append(kwargs)
        await asyncio.sleep(10)


def test_a_call_ends_by_its_deadline_retries_included() -> None:
    provider = HangingProvider()
    service = make_service(provider, timeout_s=30, deadline_s=0.05, max_retries=2)
    with pytest.raises(LLMUnavailableError):
        generate(service)
    assert len(provider.calls) == 1


def test_no_retry_when_the_pause_before_it_passes_the_deadline() -> None:
    provider = FakeProvider().queue(*[TransientLLMError("503")] * 2, Answer(value=8))
    service = make_service(provider, deadline_s=0.5, max_retries=2, fallback_model="backup")
    with pytest.raises(LLMUnavailableError):
        generate(service)  # the pause before the second round is 1 s
    assert [c["model"] for c in provider.calls] == ["main", "backup"]
