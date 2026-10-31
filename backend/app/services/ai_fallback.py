"""Planning without the LLM, for when it is unavailable (down, out of budget, refusing).

The request is read with simple rules (`read_request`) and places come straight from the
candidate ranking (fame, the interests the text names, closeness to the hotel and the
must-visit places). Such a plan has the right city, days and pace and the best-ranked
places for the interests it names, but not what only the LLM gives: wishes in the
traveller's own words and a note on each place. Plans say when they were made this way
(`ai_fallback`).
"""

import logging
import re
from collections.abc import Iterator

from pydantic import BaseModel

from app.catalog import CategorySlug
from app.ingest.cities import CITIES
from app.ingest.osm import normalize_name
from app.llm.base import LLMBudgetExceededError, LLMError, LLMUnavailableError
from app.llm.service import LLMService
from app.schemas.trip import Pace, TripRequest

logger = logging.getLogger(__name__)

# The plan's rationale, in place of the LLM's.
FALLBACK_RATIONALE = (
    "The AI planner is unavailable right now, so this plan has the best-known places in "
    "{city} for the interests your request names, without a note on each. Try again later "
    "for a plan made for you."
)
# A replacement's warning, in place of the LLM's choice.
REPLACE_FALLBACK_NOTE = (
    "The AI planner is unavailable right now, so the replacements are the best-ranked "
    "places nearby that fit."
)


async def ask_llm[T: BaseModel](
    llm: LLMService, *, system: str, prompt: str, schema: type[T]
) -> T | None:
    """The LLM's answer, or None when it fails: after its retries and fallback model, at
    once while its circuit is open, or when the daily token budget is used up."""
    try:
        return await llm.generate(system=system, prompt=prompt, schema=schema)
    except (LLMUnavailableError, LLMBudgetExceededError) as exc:
        logger.warning("Planning without the LLM: %s", exc)
    except LLMError:
        # Not an outage (a refused request, a bad key): worth a look.
        logger.exception("LLM failed; planning without it")
    return None


_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_NUMBERS |= {"six": 6, "seven": 7}
_DAYS = re.compile(rf"\b(\d+|{'|'.join(_NUMBERS)})[\s-]*(?:full\s+)?(?:days?|nights?)\b")
_HOURS = re.compile(r"\b(\d+)[\s-]*hours?\b")

# Words (accents ignored) that name a category.
INTEREST_WORDS: dict[CategorySlug, str] = {
    "museum": r"museums?|museus?|exhibitions?",
    "gallery": r"galler(y|ies)|arts?|artworks?|paintings?",
    "landmark": r"landmarks?|sights?|sightseeing|castles?|palaces?|towers?|historic(al)?"
    r"|history|architecture",
    "monument": r"monuments?|memorials?|statues?",
    "viewpoint": r"viewpoints?|views?|panoram(a|as|ic)|miradouros?|lookouts?|sunsets?",
    "religious": r"church(es)?|cathedrals?|monaster(y|ies)|chapels?|convents?|basilicas?",
    "park": r"parks?|gardens?|nature",
    "culture": r"theat(re|res|er|ers)|operas?|concerts?|culture|cultural",
    "market": r"markets?|shopping",
    "attraction": r"zoos?|aquariums?|attractions?",
    "nightlife": r"bars?|pubs?|nightlife|clubs?|clubbing|fado",
    "restaurant": r"restaurants?|food|foodie|dinners?|lunch(es)?|eat|eating",
    "cafe": r"cafes?|coffee|pastr(y|ies)",
}
_INTERESTS = {category: re.compile(words) for category, words in INTEREST_WORDS.items()}
# A word that turns the next few into things to avoid: "no museums", "avoid churches".
_NEGATIONS = {"no", "not", "avoid", "without", "skip", "except", "hate", "dont", "nothing"}
_NEGATION_REACH = 3

# Word beginnings that set the pace; relaxed wins ("kids, but see everything").
_RELAXED = re.compile(
    r"\b(kid|child|toddler|baby|elderly|senior|grandparent|slow|relax|easy|leisure|wheelchair"
    r"|calm)"
)
_INTENSE = re.compile(r"\b(everything|intense|packed|maximum|as much as)")

# Capitalized words that are no names of places.
_NOT_NAMES = {"The", "And", "Our", "You", "Please", "Day", "Days"}
_NOT_NAMES |= {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
_NOT_NAMES |= {"January", "February", "March", "April", "June", "July", "August"}
_NOT_NAMES |= {"September", "October", "November", "December"}
# Small words inside names: "Torre de Belém", "Museum of Art".
_NAME_LINKS = {"de", "da", "do", "dos", "das", "del", "la", "el", "von", "der", "of", "the"}
_SENTENCE_ENDS = set(".!?:;\n")


def _words(text: str) -> list[str]:
    """Lowercase words without accents or apostrophes ("don't" is "dont")."""
    return re.findall(r"[a-z0-9]+", re.sub(r"['’]", "", normalize_name(text)))


def read_days(text: str) -> int:
    words = " ".join(_words(text))
    if match := _DAYS.search(words):
        number = match.group(1)
        return int(number) if number.isdigit() else _NUMBERS[number]
    if match := _HOURS.search(words):
        return max(1, -(-int(match.group(1)) // 24))
    if "long weekend" in words:
        return 3
    if "weekend" in words:
        return 2
    if re.search(r"\b(a|one)\s+week\b", words):
        return 7
    return 1


def read_interests(text: str) -> tuple[list[CategorySlug], list[CategorySlug]]:
    """Categories the text names, and those it names after a negation."""
    interests: list[CategorySlug] = []
    avoid: list[CategorySlug] = []
    words = _words(text)
    for i, word in enumerate(words):
        for category, pattern in _INTERESTS.items():
            if pattern.fullmatch(word):
                negated = _NEGATIONS & set(words[max(0, i - _NEGATION_REACH) : i])
                (avoid if negated else interests).append(category)
    avoid = list(dict.fromkeys(avoid))
    return [c for c in dict.fromkeys(interests) if c not in avoid], avoid


def read_pace(text: str) -> Pace:
    words = " ".join(_words(text))
    if _RELAXED.search(words):
        return "relaxed"
    if _INTENSE.search(words):
        return "intense"
    return "moderate"


def _city_names() -> dict[str, str]:
    """Every name of a supported city (accents ignored), to its slug."""
    return {
        normalize_name(name): city.slug
        for city in CITIES.values()
        for name in (city.slug, city.name, *city.aliases)
    }


def read_city(text: str) -> str | None:
    """The first supported city the text names, by its slug, name or an alias."""
    words = " ".join(_words(text))
    found = [
        (match.start(), slug)
        for name, slug in _city_names().items()
        if (match := re.search(rf"\b{re.escape(name)}\b", words))
    ]
    return min(found)[1] if found else None


def _names(text: str) -> Iterator[str]:
    """Runs of capitalized words, not at the start of a sentence, with the small words
    between them: "Belém", "Torre de Belém", "Sagrada Família"."""
    run: list[str] = []
    links: list[str] = []  # small words after the run, kept if a name follows
    starts_sentence = True
    for token in re.findall(r"[^\W\d_][\w'’-]*|\d+|[^\w\s]|\n", text):
        token = re.sub(r"['’]s$", "", token)  # "Gaudí's"
        word = token[0].isalpha()
        if word and not starts_sentence and token[0].isupper() and token not in _NOT_NAMES:
            if len(token) > 2:
                run += [*links, token]
                links = []
                starts_sentence = False
                continue
        elif word and run and token in _NAME_LINKS:
            links.append(token)
            continue
        if run:
            yield " ".join(run)
        run, links = [], []
        starts_sentence = token in _SENTENCE_ENDS or (starts_sentence and not word)
    if run:
        yield " ".join(run)


def read_keywords(text: str) -> list[str]:
    """Names the text gives (places, neighbourhoods), but the cities'."""
    cities = _city_names()
    return list(dict.fromkeys(n for n in _names(text) if normalize_name(n) not in cities))


def read_request(text: str) -> TripRequest:
    """The request as the LLM would parse it, by simple rules."""
    interests, avoid = read_interests(text)
    return TripRequest(
        city=read_city(text),
        days=read_days(text),
        interests=interests,
        avoid=avoid,
        pace=read_pace(text),
        keywords=read_keywords(text),
        notes="",
    )
