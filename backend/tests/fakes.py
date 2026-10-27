from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel

from app.llm.base import LLMResponse
from app.optimizer.geometry import LatLon
from app.optimizer.transit import TransitRoute


@dataclass
class FakeProvider:
    """Replays queued outcomes: a BaseModel is returned, an Exception is raised."""

    outcomes: deque[BaseModel | Exception] = field(default_factory=deque)
    calls: list[dict[str, object]] = field(default_factory=list)

    def queue(self, *outcomes: BaseModel | Exception) -> "FakeProvider":
        self.outcomes.extend(outcomes)
        return self

    async def generate[T: BaseModel](
        self, *, model: str, system: str, prompt: str, schema: type[T], max_output_tokens: int
    ) -> LLMResponse[T]:
        self.calls.append({"model": model, "system": system, "prompt": prompt, "schema": schema})
        outcome = self.outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, schema), f"queued {type(outcome)}, asked for {schema}"
        return LLMResponse(parsed=outcome, input_tokens=100, output_tokens=20)


@dataclass
class FakeTransit:
    """Answers every leg with `answer(origin, destination)`; records the requests."""

    answer: Callable[[LatLon, LatLon], TransitRoute | None]
    calls: list[list[tuple[LatLon, LatLon]]] = field(default_factory=list)

    async def routes(self, pairs: Sequence[tuple[LatLon, LatLon]]) -> list[TransitRoute | None]:
        self.calls.append(list(pairs))
        return [self.answer(a, b) for a, b in pairs]

    @property
    def asked(self) -> list[tuple[LatLon, LatLon]]:
        return [pair for call in self.calls for pair in call]
