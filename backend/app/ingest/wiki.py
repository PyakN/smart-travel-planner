"""Photos and short descriptions for places: Wikidata, Wikimedia Commons, English Wikipedia.

A place links to Wikidata through its OSM `wikidata` tag. Wikidata gives the main image
(P18, a Commons file), a one-line English description and the English Wikipedia article;
Commons gives a thumbnail with its author and licence; Wikipedia gives the article intro.
OSM `wikimedia_commons` / `image` / `wikipedia` tags fill in when Wikidata has nothing.
"""

import asyncio
import html
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

import httpx

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
# Wikimedia's robot policy wants a client name, contact details and the library; requests
# without them get 403 (https://meta.wikimedia.org/wiki/User-Agent_policy).
USER_AGENT = (
    "smart-travel-planner/0.1 (https://github.com/PyakN/smart-travel-planner; POI enrichment) "
    f"python-httpx/{httpx.__version__}"
)
SPARQL_BATCH, COMMONS_BATCH, WIKIPEDIA_BATCH = 100, 50, 20
# The query service and the APIs time out or throttle now and then: retry with pauses.
ATTEMPTS = 3
RETRY_DELAY_S = 2.0
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
THUMB_WIDTH = 500
DESCRIPTION_MAX_CHARS = 300
CREDIT_MAX_CHARS = 120
QID = re.compile(r"^Q\d+$")


@dataclass(frozen=True)
class WikidataInfo:
    image: str | None  # Commons file name without "File:", e.g. "Teatro da Trindade 2017.jpg"
    description: str | None  # Wikidata's one-line English description
    article: str | None  # English Wikipedia title


@dataclass(frozen=True)
class Photo:
    url: str  # thumbnail, about THUMB_WIDTH px wide
    page_url: str  # Commons file page: author, licence, full size
    credit: str | None  # "Author, licence"


def _batches[T](items: Sequence[T], size: int) -> Iterable[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


async def _get_json(
    client: httpx.AsyncClient, method: str, url: str, **kwargs: Any
) -> dict[str, Any]:
    """JSON answer of a Wikimedia endpoint, retrying timeouts, throttling and 5xx."""
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    for attempt in range(1, ATTEMPTS + 1):
        try:
            response = await client.request(method, url, headers=headers, timeout=60, **kwargs)
            if response.status_code not in RETRY_STATUS or attempt == ATTEMPTS:
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
                return payload
        except httpx.TransportError:
            if attempt == ATTEMPTS:
                raise
        await asyncio.sleep(RETRY_DELAY_S * 2 ** (attempt - 1))
    raise AssertionError("unreachable")


def _file_name(title: str) -> str:
    """Commons file name as MediaWiki normalizes it: no prefix, spaces, first letter upper."""
    name = title.removeprefix("File:").replace("_", " ").strip()
    return name[:1].upper() + name[1:]


# --- Wikidata ---------------------------------------------------------------------------


def sparql_query(qids: Sequence[str]) -> str:
    values = " ".join(f"wd:{q}" for q in qids if QID.match(q))
    return f"""SELECT ?item ?image ?description ?article WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item wdt:P18 ?image }}
  OPTIONAL {{ ?item schema:description ?description FILTER(LANG(?description) = "en") }}
  OPTIONAL {{ ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> }}
}}"""


def parse_sparql(payload: Mapping[str, Any]) -> dict[str, WikidataInfo]:
    """One entry per item; the first image and article win when there are several."""
    found: dict[str, dict[str, str]] = {}
    for binding in payload["results"]["bindings"]:
        qid = binding["item"]["value"].rsplit("/", 1)[-1]
        fields = found.setdefault(qid, {})
        for key in ("image", "description", "article"):
            if key in binding and key not in fields:
                fields[key] = binding[key]["value"]
    return {
        qid: WikidataInfo(
            image=_file_name(unquote(f["image"].rsplit("/", 1)[-1])) if "image" in f else None,
            description=f.get("description"),
            article=unquote(f["article"].rsplit("/", 1)[-1]) if "article" in f else None,
        )
        for qid, f in found.items()
    }


async def fetch_wikidata(client: httpx.AsyncClient, qids: Sequence[str]) -> dict[str, WikidataInfo]:
    found: dict[str, WikidataInfo] = {}
    for batch in _batches(sorted(set(qids)), SPARQL_BATCH):
        payload = await _get_json(
            client,
            "POST",
            WIKIDATA_SPARQL_URL,
            data={"query": sparql_query(batch)},
            headers={"Accept": "application/sparql-results+json"},
        )
        found |= parse_sparql(payload)
    return found


# --- Commons ----------------------------------------------------------------------------


def _strip_html(value: str) -> str:
    """Plain text of an HTML snippet, without bare URLs (authors often paste profile links)."""
    text = re.sub(r"https?://\S+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value)))
    return " ".join(text.split()).strip(" ,;")


def _credit(extmetadata: Mapping[str, Any]) -> str | None:
    parts = [
        _strip_html(extmetadata[key]["value"])
        for key in ("Artist", "LicenseShortName")
        if key in extmetadata
    ]
    credit = ", ".join(p for p in parts if p)
    return credit[:CREDIT_MAX_CHARS] or None


def _aliases(query: Mapping[str, Any]) -> dict[str, str]:
    """Requested title -> final page title, through MediaWiki's normalization and redirects."""
    steps = {
        item["from"]: item["to"]
        for key in ("normalized", "redirects")
        for item in query.get(key, [])
    }
    resolved = {}
    for start in steps:
        title, seen = start, set()
        while title in steps and title not in seen:
            seen.add(title)
            title = steps[title]
        resolved[start] = title
    return resolved


def parse_imageinfo(payload: Mapping[str, Any]) -> dict[str, Photo]:
    """Photos keyed by file name (as `_file_name` normalizes it)."""
    query = payload.get("query", {})
    photos: dict[str, Photo] = {}
    for page in query.get("pages", []):
        info = (page.get("imageinfo") or [None])[0]
        if not info or "thumburl" not in info:
            continue
        photos[_file_name(page["title"])] = Photo(
            url=info["thumburl"].split("?", 1)[0],  # drop Wikimedia's tracking parameters
            page_url=info["descriptionurl"],
            credit=_credit(info.get("extmetadata", {})),
        )
    for requested, final in _aliases(query).items():
        if _file_name(final) in photos:
            photos.setdefault(_file_name(requested), photos[_file_name(final)])
    return photos


async def fetch_photos(client: httpx.AsyncClient, files: Sequence[str]) -> dict[str, Photo]:
    found: dict[str, Photo] = {}
    for batch in _batches(sorted({_file_name(f) for f in files}), COMMONS_BATCH):
        payload = await _get_json(
            client,
            "GET",
            COMMONS_API_URL,
            params={
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": str(THUMB_WIDTH),
                "iiextmetadatafilter": "Artist|LicenseShortName",
                "titles": "|".join(f"File:{f}" for f in batch),
            },
        )
        found |= parse_imageinfo(payload)
    return found


# --- Wikipedia --------------------------------------------------------------------------


def _title(title: str) -> str:
    return title.replace("_", " ").strip()


def clean_extract(text: str) -> str | None:
    """The intro without pronunciations and other asides, cut at a sentence boundary."""
    previous = None
    while previous != text:  # innermost parentheses first, so nested ones go too
        previous, text = text, re.sub(r"\s*\([^()]*\)", "", text)
    text = " ".join(text.split())
    if len(text) > DESCRIPTION_MAX_CHARS:
        cut = text.rfind(". ", 0, DESCRIPTION_MAX_CHARS)
        text = text[: cut + 1] if cut > 0 else text[: DESCRIPTION_MAX_CHARS - 1].rstrip() + "…"
    return text or None


def parse_extracts(payload: Mapping[str, Any]) -> dict[str, str]:
    """Cleaned intros keyed by article title (requested spellings included)."""
    query = payload.get("query", {})
    extracts = {
        _title(page["title"]): cleaned
        for page in query.get("pages", [])
        if page.get("extract") and (cleaned := clean_extract(page["extract"]))
    }
    for requested, final in _aliases(query).items():
        if _title(final) in extracts:
            extracts.setdefault(_title(requested), extracts[_title(final)])
    return extracts


async def fetch_extracts(client: httpx.AsyncClient, titles: Sequence[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for batch in _batches(sorted({_title(t) for t in titles}), WIKIPEDIA_BATCH):
        payload = await _get_json(
            client,
            "GET",
            WIKIPEDIA_API_URL,
            params={
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "prop": "extracts",
                "exintro": "1",
                "explaintext": "1",
                "exsentences": "2",
                "exlimit": str(WIKIPEDIA_BATCH),
                "redirects": "1",
                "titles": "|".join(batch),
            },
        )
        found |= parse_extracts(payload)
    return found


# --- Choosing per place -----------------------------------------------------------------


def photo_file(tags: Mapping[str, str], info: WikidataInfo | None) -> str | None:
    """Commons file for a place: Wikidata's image, else one named in the OSM tags."""
    if info and info.image:
        return info.image
    commons = tags.get("wikimedia_commons", "")
    if commons.startswith("File:"):
        return _file_name(commons)
    image = tags.get("image", "")
    for marker in ("commons.wikimedia.org/wiki/File:", "/wikipedia/commons/"):
        if marker in image:
            # .../wiki/File:Name.jpg or .../wikipedia/commons/a/ab/Name.jpg
            return _file_name(unquote(image.rsplit("/", 1)[-1].split("?", 1)[0]))
    return None


def article_title(tags: Mapping[str, str], info: WikidataInfo | None) -> str | None:
    if info and info.article:
        return _title(info.article)
    wikipedia = tags.get("wikipedia", "")
    return _title(wikipedia[3:]) if wikipedia.startswith("en:") else None


def description(
    tags: Mapping[str, str], info: WikidataInfo | None, extracts: Mapping[str, str]
) -> str | None:
    """Wikipedia intro, else Wikidata's one-liner, else an English OSM description."""
    title = article_title(tags, info)
    if title and title in extracts:
        return extracts[title]
    if info and info.description:
        return info.description[:1].upper() + info.description[1:] + "."
    english = tags.get("description:en")
    return english[:DESCRIPTION_MAX_CHARS] if english else None
