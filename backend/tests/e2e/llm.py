"""The LLM of the end-to-end tests: it answers at once, and the same way every time.

It reads requests by the rules plans fall back on (app.services.ai_fallback) and chooses
the first candidates it is offered, with a note on each. A request that says `OUTAGE`
makes it fail, as an outage would, so the browser sees a plan made without it.
"""

import re

from pydantic import BaseModel

from app.llm.base import LLMResponse, TransientLLMError
from app.llm.service import CircuitBreaker, LLMService
from app.schemas.trip import PlaceNote, PlaceSelection, TripRequest
from app.services.ai_fallback import read_request

OUTAGE = "llm-outage"
NOTE = "Chosen by the test LLM."
RATIONALE = "The first candidates, as the test LLM always chooses."


def _choose(prompt: str) -> PlaceSelection:
    match = re.search(r"Number of places to choose: (\d+)", prompt)
    count = int(match.group(1)) if match else 0
    lines = prompt.split("\nCandidates (", 1)[1].splitlines()[1:]
    chosen = [int(line.split(" | ", 1)[0]) for line in lines if line.strip()][:count]
    return PlaceSelection(
        place_ids=chosen,
        notes=[PlaceNote(place_id=place_id, note=NOTE) for place_id in chosen],
        rationale=RATIONALE,
    )


class E2EProvider:
    async def generate[T: BaseModel](
        self, *, model: str, system: str, prompt: str, schema: type[T], max_output_tokens: int
    ) -> LLMResponse[T]:
        if OUTAGE in prompt:
            raise TransientLLMError("an outage of the end-to-end tests")
        if schema is TripRequest:
            answer: BaseModel = read_request(prompt.split("<<<\n", 1)[1].rsplit("\n>>>", 1)[0])
        elif schema is PlaceSelection:
            answer = _choose(prompt)
        else:
            raise TypeError(f"no scripted answer for {schema.__name__}")
        return LLMResponse(
            parsed=schema.model_validate(answer.model_dump()), input_tokens=0, output_tokens=0
        )


def e2e_llm() -> LLMService:
    """Fails at once in an outage, and never stops calling: the outage one test asks for
    must not reach the others."""
    return LLMService(
        E2EProvider(), model="e2e", max_retries=0, circuit=CircuitBreaker(threshold=10**9)
    )
