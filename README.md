# Smart AI Travel Planner

A travel planner with a two-layer architecture:

1. **LLM** (Gemini / OpenAI) parses the user's request and selects interesting places from our database.
2. **Geo-optimizer** (TSP / PostGIS) reorders those places into the shortest walking route, with no zigzags.

Stack: FastAPI · PostgreSQL + PostGIS · Next.js + Leaflet. Roadmap: [PROJECT_PLAN.md](PROJECT_PLAN.md). Dev rules: [CLAUDE.md](CLAUDE.md).

## Layout

```
backend/    FastAPI app (Python 3.12+)
frontend/   Next.js app with a Leaflet map
docs/       Notes and benchmarks
```

## Getting started

Prerequisites: Docker, Python 3.12+, Node.js 24+.

```bash
# 1. Environment: copy the template and set a real password
cp .env.example .env

# 2. Database (PostGIS)
docker compose up -d --wait

# 3. Backend tooling
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows (Git Bash); on macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]" pre-commit

# 4. Schema + data (from backend/)
alembic upgrade head
python -m app.ingest lisbon        # ~2k POIs from OpenStreetMap, ~1 min
python -m app.ingest.enrich lisbon # photos + descriptions from Wikimedia, ~1 min

# 5. Frontend
cd ../frontend
npm ci

# 6. Git hooks (run from the repo root)
cd ..
pre-commit install
```

Run it: start the API (`cd backend && uvicorn app.main:app --reload`) and the UI (`cd frontend && npm run dev`), then open http://localhost:3000. The UI proxies `/api/*` to the backend; see [frontend/README.md](frontend/README.md).

The importer caches the raw Overpass response in `backend/data/raw/`. Re-runs use the cache and upsert by OSM id; pass `--refresh` to fetch fresh data.

`app.ingest.enrich` adds what the stop cards show: a photo from Wikimedia Commons (thumbnail, author and licence), and a short description from English Wikipedia or Wikidata. Opening hours and websites come from the OSM tags. Its answers are cached in `backend/data/raw/<city>-wiki.json` (`--refresh` asks again). Lisbon: 604 places with a photo, 414 with a description.

## API

```bash
cd backend
uvicorn app.main:app --reload      # http://localhost:8000/docs for interactive docs
```

| Endpoint | Description |
|---|---|
| `GET /health` | Service and database status |
| `GET /places` | Search: `q` (name contains, accents ignored), `city`, `category` (repeatable), `bbox=west,south,east,north`, or `lat`+`lon`+`radius_m` (sorted by distance); `limit` / `offset` |
| `GET /places/{id}` | One place |
| `GET /categories` | Categories with place counts (optional `city`) |
| `POST /plan` | **Plan a trip from text**: `{"text", "start"?: {"lat", "lon", "round_trip"}, "must_visit"?: [place ids], "modes"?: ["walk", "transit"], "start_date"?: "YYYY-MM-DD", "weather_aware"?: bool}` → dated days with ordered, timed stops (photo, description, personal note, opening hours, forecast) and map geometry. Saved; returns `id` |
| `GET /plans/{id}` | A saved plan |
| `POST /plans/{id}/replace` | **Replace stops of a day**: `{"day", "place_ids"}` → a new saved version (`parent_id` = this plan), with an `edit` listing what was replaced, added and adjusted |

Example: museums and viewpoints within 400 m of Praça do Comércio:

```
GET /places?lat=38.7075&lon=-9.1364&radius_m=400&category=museum&category=viewpoint
```

Plan a trip (needs an LLM key in `.env`):

```bash
curl -X POST localhost:8000/plan -H "Content-Type: application/json" \
  -d '{"text": "2 days in Lisbon: viewpoints, the castle and Belém", "start": {"lat": 38.7139, "lon": -9.1394}}'
```

Must-visit places are ids from `GET /places?q=...`. They always get a slot on some day if they fit its time budget: trimmed only after every optional stop, and moved to another day when their own day overflows. `modes`: walking only rides nothing, transit only rides every leg over 1 km, both (the default) ride legs over 2.5 km.

Replacing stops (`POST /plans/{id}/replace`):
- The ticked stops leave the day. Nothing planned on any day, or rejected in an earlier swap of the plan, comes back.
- Candidates are ranked around the stops that stay and must fit the freed time; the LLM picks the replacements by id.
- Only that day is re-optimized; the other days are copied unchanged.
- **Last resort:** a day left sparse (fewer stops, or an hour shorter) gets nearby fillers, and a one-note day (one kind of place is over half of 4+ stops) swaps one unticked stop of that kind. Must-visit stops and the new replacements are never touched, and every adjustment is reported.

Error statuses:
- **422:** the request can't be planned, for example an unsupported city.
- **429:** the daily LLM token budget is used up.
- **502:** the LLM rejected the request.
- **503:** the LLM is unavailable or not configured.
- **504:** planning timed out.

## LLM layer

The LLM never invents places. A request goes through four steps:

1. **Parse:** the request text becomes a `TripRequest` (city, days, interests, avoid, pace, keywords).
2. **Candidates:** SQL ranks the city's places by notability, interests and keywords, plus closeness to the hotel and the must-visit places (PostGIS distance; full weight at the anchor, none beyond 2.5 km on foot or 5 km with transit).
3. **Select:** the LLM fills the slots the must-visit places leave, picking ids from that candidate list (it sees the distances), and writes a one-sentence note per place on why it suits the traveller.
4. **Guard:** a deterministic check drops any id that isn't a candidate, and places with the same name as one already chosen (OSM maps some sights twice).

Configure it in `.env`: `LLM_PROVIDER`, the matching API key, and optionally `LLM_MODEL` and `LLM_FALLBACK_MODEL`. For real public transport routes, also set `HERE_API_KEY` (see [Route optimizer](#route-optimizer)); for the weather, `OPENWEATHER_API_KEY` (see [Weather](#weather)).

```bash
cd backend
python evals/selection_eval.py     # live eval against the real LLM + DB (costs a few cents)
```

## Route optimizer

`app/optimizer/` turns the selected places into days and walking order:

- **Distances:** an OSRM foot routing matrix, falling back to haversine × 1.3. Set `ROUTING_PROVIDER` to choose.
- **Order within a day:** a TSP solver (nearest neighbour + 2-opt + Or-opt).
- **Split into days:** several strategies are tried and the shortest wins, with every day kept within the pace's time budget.
- **Schedule:** arrival and departure times for each stop.
- **Transit:** legs over 2.5 km (e.g. the centre to Belém) are ridden by metro, tram, bus or train when that is faster than walking. Walking-only trips ride nothing; transit-only trips ride every leg over 1 km. The optimizer minimises total travel time; each stop says how to get there (`travel_mode`), and the map geometry is split into walking and transit segments.
- **Real timetables:** with `HERE_API_KEY` set, ride times and routes come from the HERE Public Transit API v8 (midday on the next weekday). HERE has no transit matrix, so the plan is made with estimated ride times (10 min overhead + 15 km/h), the real routes of the legs it rides are fetched, and the plan is made again until it only rides known routes (at most 3 rounds; answers are cached in memory). A ridden leg is drawn along the line and its stop lists the rides (`rides`: line, colour, where to get on and off, stops, direction). Without a key, or when HERE fails, rides keep the estimate; `transit_source` in the response says which (`here`, `estimate`, `mixed`).
- **Must-visit stops** are trimmed last and, if their day overflows, moved to the day that loses the fewest optional stops.
- **Weather** (weather-aware plans only): outdoor stops are kept out of rain, fog and darkness; see [Weather](#weather).

Results against LLM-only ordering are in [docs/benchmark.md](docs/benchmark.md): **55% less walking than the selection order, and on par with an itinerary the LLM arranged itself, with zero route crossings.**

```bash
cd backend
python evals/route_benchmark.py    # live benchmark (LLM + OSRM)
```

## Weather

Set `OPENWEATHER_API_KEY` (a free OpenWeatherMap key is enough; new keys can take a couple of hours to activate). `app/services/weather_service.py` fetches the [5 day / 3 hour forecast](https://openweathermap.org/forecast5) for the city (temperature, chance of rain or snow, fog, visibility, sunrise and sunset), caches it for 30 minutes, and maps it to the trip's days in the city's time zone. Without a key, or when OpenWeatherMap fails, plans simply have no weather.

**Every plan shows it.** Days have a date (`start_date`, tomorrow by default) and a forecast for their sightseeing hours; each stop says whether it is `outdoor` and gets the forecast at its arrival, with a `warning` when rain, fog or darkness spoils an outdoor visit. Days past the forecast's 5-day reach have no weather.

**Weather-aware plans** (`"weather_aware": true`, the "Optimize route based on weather conditions" checkbox) use it to plan:

- **Indoor or outdoor:** from the category and OSM tags. Museums, galleries, churches, theatres, palaces, monasteries, market halls and the aquarium are indoor; viewpoints, parks, statues, castle walls, aqueducts, open-air markets and most attractions are outdoor.
- **Bad minutes:** each minute of a day gets a badness from 0 to 1 for outdoor sights: rain, drizzle, snow and thunderstorms by their chance, fog (visibility under 1 km) as 1, haze or mist as 0.5, and darkness outside sunrise to sunset as 1.
- **Selection:** the LLM sees each day's weather and which candidates are outdoor, and may pick at most as many outdoor places as the dry, light share of the sightseeing hours allows. A guard enforces it: the least important outdoor picks give their slot to the best-ranked indoor candidates left, which come from the same interest- and distance-ranked pool. Must-visit places are never swapped, and every swap is listed (`weather_swaps`).
- **Routing** (soft time windows): the plan is made for travel time as before, then an outdoor visit costs up to 45 more minutes of travel for its share of bad minutes. Days are matched to the dates that suit them, each day is reordered, and outdoor stops caught in bad weather move to another day, alone or in exchange for an indoor stop, while that pays off. Days keep to their time budget, and dry, light days keep the plain plan. On random trips, outdoor visits meet 80–100% less bad weather for 5–20% more travel.
- **Replacing stops** fetches the latest forecast for the day; the LLM sees it and the day is ordered around it.

Limits: days still start at 09:30 and never wait for rain to pass; and the forecast's 3-hour steps blur the exact hour a shower starts.

## Everyday commands

```bash
docker compose up -d --wait        # start the database
docker compose down                # stop it (data persists in the pgdata volume)

cd backend
alembic upgrade head               # apply migrations
alembic check                      # models and migrations in sync?
ruff check . && ruff format .      # lint + format
mypy                               # type check
pytest                             # all tests (integration tests need Docker)
pytest -m "not integration"        # unit tests only

pre-commit run --all-files         # run every hook manually
```

## Secrets

Never commit `.env`. Only `.env.example` lives in git. A pre-commit hook blocks `.env` files, and gitleaks scans for hardcoded secrets.
