"""Add photos, short descriptions and fame to a city's places (run after the OSM import).

Usage (from backend/):  python -m app.ingest.enrich lisbon [--refresh]

Sources: Wikidata, Wikimedia Commons and Wikipedia (see app.ingest.wiki). Answers, misses
included, are cached in data/raw/<city>-wiki.json, so re-runs only ask about what is new.
"""

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Place
from app.db.session import create_engine, create_sessionmaker
from app.geo import BBox
from app.ingest.cities import CITIES, City
from app.ingest.wiki import (
    Photo,
    WikidataInfo,
    article_title,
    description,
    fetch_extracts,
    fetch_photos,
    fetch_wikidata,
    photo_file,
    wikipedia_languages,
)

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
# Wikidata may place an item a little off its city's bbox (a fort on the shore).
AREA_MARGIN_DEG = 0.05


@dataclass
class WikiCache:
    """What each source said; None records a miss so it is not asked again."""

    wikidata: dict[str, WikidataInfo | None] = field(default_factory=dict)
    photos: dict[str, Photo | None] = field(default_factory=dict)
    extracts: dict[str, str | None] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "WikiCache":
        if not path.exists():
            return cls()
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            # Items cached before Wikipedias were counted, or coordinates asked for, are
            # asked again.
            wikidata={
                k: WikidataInfo(**v | {"coords": tuple(v["coords"]) if v["coords"] else None})
                if v
                else None
                for k, v in raw["wikidata"].items()
                if not v or {"wikipedias", "coords"} <= v.keys()
            },
            photos={k: Photo(**v) if v else None for k, v in raw["photos"].items()},
            extracts=raw["extracts"],
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            "wikidata": {k: asdict(v) if v else None for k, v in self.wikidata.items()},
            "photos": {k: asdict(v) if v else None for k, v in self.photos.items()},
            "extracts": self.extracts,
        }
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")


@dataclass(frozen=True)
class EnrichStats:
    places: int
    photos: int
    descriptions: int
    in_wikipedia: int
    not_the_place: int = 0


def about_the_place(info: WikidataInfo | None, area: BBox) -> bool:
    """Whether the Wikidata item OSM links is the place itself: Wikidata places it in the
    city. OSM often links what a place is about instead: the person a statue or a grave is
    of, a zoo's animals, an event, an organisation, another cast of a sculpture. Their fame,
    photo, description and name are not the place's."""
    if info is None or info.coords is None:
        return False
    lat, lon = info.coords
    margin = AREA_MARGIN_DEG
    return (
        area.south - margin <= lat <= area.north + margin
        and area.west - margin <= lon <= area.east + margin
    )


async def enrich_city(
    session: AsyncSession, client: httpx.AsyncClient, city: City, cache: WikiCache
) -> EnrichStats:
    rows = (
        await session.execute(
            select(Place.id, Place.wikidata, Place.tags).where(Place.city == city.slug)
        )
    ).all()

    qids = sorted({qid for _, qid, _ in rows if qid and qid not in cache.wikidata})
    found = await fetch_wikidata(client, qids)
    cache.wikidata |= {qid: found.get(qid) for qid in qids}
    linked = {place_id: cache.wikidata.get(qid) if qid else None for place_id, qid, _ in rows}
    info = {pid: i if about_the_place(i, city.bbox) else None for pid, i in linked.items()}
    not_the_place = {pid for pid, i in linked.items() if i is not None and info[pid] is None}
    # The Wikipedia article OSM links for such a place is about the same thing.
    places: list[tuple[int, dict[str, str]]] = [
        (pid, {k: v for k, v in tags.items() if k != "wikipedia"} if pid in not_the_place else tags)
        for pid, _, tags in rows
    ]

    files = {pid: photo_file(tags, info[pid]) for pid, tags in places}
    new_files = sorted({f for f in files.values() if f and f not in cache.photos})
    photos = await fetch_photos(client, new_files)
    cache.photos |= {f: photos.get(f) for f in new_files}

    titles = {t for pid, tags in places if (t := article_title(tags, info[pid]))}
    new_titles = sorted(t for t in titles if t not in cache.extracts)
    extracts = await fetch_extracts(client, new_titles)
    cache.extracts |= {t: extracts.get(t) for t in new_titles}
    known_extracts = {t: e for t, e in cache.extracts.items() if e}

    updates: list[dict[str, Any]] = []
    for place_id, tags in places:
        file = files[place_id]
        photo = cache.photos.get(file) if file else None
        updates.append(
            {
                "id": place_id,
                "description": description(tags, info[place_id], known_extracts),
                "image_url": photo.url if photo else None,
                "image_page_url": photo.page_url if photo else None,
                "image_credit": photo.credit if photo else None,
                "wikipedia_languages": wikipedia_languages(tags, info[place_id]),
            }
        )
    if updates:
        await session.execute(update(Place), updates)
    await session.commit()
    return EnrichStats(
        places=len(updates),
        photos=sum(u["image_url"] is not None for u in updates),
        descriptions=sum(u["description"] is not None for u in updates),
        in_wikipedia=sum(u["wikipedia_languages"] > 0 for u in updates),
        not_the_place=len(not_the_place),
    )


async def run(city: str, refresh: bool) -> None:
    cache_file = CACHE_DIR / f"{city}-wiki.json"
    cache = WikiCache() if refresh else WikiCache.load(cache_file)
    engine = create_engine()
    try:
        async with httpx.AsyncClient() as client, create_sessionmaker(engine)() as session:
            stats = await enrich_city(session, client, CITIES[city], cache)
    finally:
        cache.save(cache_file)
        await engine.dispose()
    print(
        f"{stats.places} places: {stats.photos} with a photo, "
        f"{stats.descriptions} with a description, {stats.in_wikipedia} in Wikipedia; "
        f"{stats.not_the_place} linked to a Wikidata item that is not the place "
        f"(cache: {cache_file})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city", choices=sorted(CITIES))
    parser.add_argument("--refresh", action="store_true", help="ignore the cached answers")
    args = parser.parse_args()
    asyncio.run(run(args.city, args.refresh))


if __name__ == "__main__":
    main()
