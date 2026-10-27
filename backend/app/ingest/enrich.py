"""Add photos and short descriptions to a city's places (run after the OSM import).

Usage (from backend/):  python -m app.ingest.enrich lisbon [--refresh]

Sources: Wikidata, Wikimedia Commons and English Wikipedia (see app.ingest.wiki). Answers,
misses included, are cached in data/raw/<city>-wiki.json, so re-runs only ask about what
is new.
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
from app.ingest.cities import CITIES
from app.ingest.wiki import (
    Photo,
    WikidataInfo,
    article_title,
    description,
    fetch_extracts,
    fetch_photos,
    fetch_wikidata,
    photo_file,
)

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


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
            wikidata={k: WikidataInfo(**v) if v else None for k, v in raw["wikidata"].items()},
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


async def enrich_city(
    session: AsyncSession, client: httpx.AsyncClient, city: str, cache: WikiCache
) -> EnrichStats:
    rows = (
        await session.execute(
            select(Place.id, Place.wikidata, Place.tags).where(Place.city == city)
        )
    ).all()

    qids = sorted({qid for _, qid, _ in rows if qid and qid not in cache.wikidata})
    found = await fetch_wikidata(client, qids)
    cache.wikidata |= {qid: found.get(qid) for qid in qids}
    info = {place_id: cache.wikidata.get(qid) if qid else None for place_id, qid, _ in rows}

    files = {pid: photo_file(tags, info[pid]) for pid, _, tags in rows}
    new_files = sorted({f for f in files.values() if f and f not in cache.photos})
    photos = await fetch_photos(client, new_files)
    cache.photos |= {f: photos.get(f) for f in new_files}

    titles = {t for pid, _, tags in rows if (t := article_title(tags, info[pid]))}
    new_titles = sorted(t for t in titles if t not in cache.extracts)
    extracts = await fetch_extracts(client, new_titles)
    cache.extracts |= {t: extracts.get(t) for t in new_titles}
    known_extracts = {t: e for t, e in cache.extracts.items() if e}

    updates = []
    for place_id, _, tags in rows:
        file = files[place_id]
        photo = cache.photos.get(file) if file else None
        updates.append(
            {
                "id": place_id,
                "description": description(tags, info[place_id], known_extracts),
                "image_url": photo.url if photo else None,
                "image_page_url": photo.page_url if photo else None,
                "image_credit": photo.credit if photo else None,
            }
        )
    if updates:
        await session.execute(update(Place), updates)
    await session.commit()
    return EnrichStats(
        places=len(updates),
        photos=sum(u["image_url"] is not None for u in updates),
        descriptions=sum(u["description"] is not None for u in updates),
    )


async def run(city: str, refresh: bool) -> None:
    cache_file = CACHE_DIR / f"{city}-wiki.json"
    cache = WikiCache() if refresh else WikiCache.load(cache_file)
    engine = create_engine()
    try:
        async with httpx.AsyncClient() as client, create_sessionmaker(engine)() as session:
            stats = await enrich_city(session, client, city, cache)
    finally:
        cache.save(cache_file)
        await engine.dispose()
    print(
        f"{stats.places} places: {stats.photos} with a photo, "
        f"{stats.descriptions} with a description (cache: {cache_file})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city", choices=sorted(CITIES))
    parser.add_argument("--refresh", action="store_true", help="ignore the cached answers")
    args = parser.parse_args()
    asyncio.run(run(args.city, args.refresh))


if __name__ == "__main__":
    main()
