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
python -m app.ingest lisbon        # ~2.7k POIs from OpenStreetMap, ~1 min
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
| `POST /plan` | **Plan a trip from text**: `{"text", "start"?: {"lat", "lon", "round_trip"}, "must_visit"?: [place ids], "modes"?: ["walk", "transit"], "start_date"?: "YYYY-MM-DD", "weather_aware"?: bool, "day_start"?: "HH:MM", "day_end"?: "HH:MM", "first_day_start"?: "HH:MM"}` → dated days with their hours and ordered, timed stops (photo, description, personal note, opening hours, free time before them, forecast) and map geometry. Saved; returns `id` |
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
- **Day hours and opening times:** every day has its own hours, and places are only visited when they are open and, outdoors, in daylight; see [Day hours and evenings](#day-hours-and-evenings).
- **Weather** (weather-aware plans only): outdoor stops are kept out of rain and fog; see [Weather](#weather).

Results against LLM-only ordering are in [docs/benchmark.md](docs/benchmark.md): **55% less walking than the selection order, and on par with an itinerary the LLM arranged itself, with zero route crossings.**

```bash
cd backend
python evals/route_benchmark.py    # live benchmark (LLM + OSRM)
```

## Day hours and evenings

`day_start` and `day_end` (the form's Start and End, 09:30 to 21:30 by default) are every
day's hours in the city's time; an end before the start runs to the next morning (16:00 to
03:00). `first_day_start` gives the first day a later start: the form fills it in with the
current time in Lisbon when the trip starts today, and later days keep their own start. A
trip that starts today never starts before now (the backend rounds up to the quarter hour
and says so in the warnings).

- **The pace is a share of the hours:** relaxed ½, moderate ⅔, intense ⅚ of them go to
  travel and visits, the rest to meals and rest. The default day plans exactly as before (8 h
  of a 12 h day at a moderate pace); a day from 16:00 to 21:30 gets 3 h 40 min and 3 places
  instead of 6.
- **When places can be visited** (`app/catalog.py`, `hours` on every stop): indoor sights
  close at 20:00 (`day`), outdoor sights need daylight (`daylight`), bars, pubs, clubs, fado
  houses and restaurants open at 20:00 (`night`), and lit squares and venues whose OSM
  opening hours run past 22:00 suit both (`any`). Sunrise and sunset come from the sunrise
  equation for every trip day (`app/sun.py`), or from the forecast on weather-aware plans.
- **Routing with time windows:** a visit that comes early waits for the place to open (the
  stop's `wait_min`, shown as free time), and none may run past closing time or sunset:
  a day that breaks that is reordered, else its least important stop with such hours is
  dropped (places that cannot be visited that day at all first) and the plan says so.
  Days must also end by the end of their hours; days with shorter hours get fewer stops.
- **Selection:** each day is split into what it holds before 20:00 (and how much of that
  is in daylight) and after. The LLM is told, sees when each candidate can be visited, and
  gets bars and up to a few restaurants in pools of their own for days with evenings (days
  without evenings get none unless named). A guard swaps picks the hours cannot take:
  evening places beyond the evening, restaurants beyond one dinner an evening, outdoor
  sights beyond the daylight, places closed at night beyond the time before 20:00. Swaps
  are listed in `hours_swaps`.
- **Data:** `python -m app.ingest lisbon --refresh` imports bars, pubs, clubs and music
  venues (`nightlife`), fado and Wikidata-notable restaurants (`restaurant`) and named
  squares (`landmark`), skipping venues named as closed: 406, 48 and ~90 in Lisbon.

Limits: indoor sights all close at 20:00 and open whenever the day starts, whatever their
own opening hours say (Museu do Fado closes at 18:00); a day only waits for places to
open, it never takes a break in the middle.

## Weather

Set `OPENWEATHER_API_KEY` (a free OpenWeatherMap key is enough; new keys can take a couple of hours to activate). `app/services/weather_service.py` fetches the [5 day / 3 hour forecast](https://openweathermap.org/forecast5) for the city (temperature, chance of rain or snow, fog, visibility, sunrise and sunset), caches it for 30 minutes, and maps it to the trip's days in the city's time zone. Without a key, or when OpenWeatherMap fails, plans simply have no weather.

**Only weather-aware plans use it** (`"weather_aware": true`, the "Optimize route based on weather conditions" checkbox); other plans never ask for the forecast. Days have a date (`start_date`, tomorrow by default) and the forecast of their hours, in the 3-hour steps those overlap (the next morning's too for days that end after midnight): rain in the morning does not matter to a day that starts at 16:00. Each stop says whether it is `outdoor` and gets the forecast at its arrival, with a `warning` when rain or fog (or, for sights that need daylight, darkness) spoils an outdoor visit. Days past the forecast's 5-day reach have no weather.

They use it to plan:

- **Indoor or outdoor:** from the category and OSM tags. Museums, galleries, churches, theatres, palaces, monasteries, market halls and the aquarium are indoor; viewpoints, parks, statues, castle walls, aqueducts, open-air markets and most attractions are outdoor.
- **Bad minutes:** each minute of a day gets a badness from 0 to 1 for outdoor sights: rain, drizzle, snow and thunderstorms by their chance, fog (visibility under 1 km) as 1, and haze or mist as 0.5. Darkness is left to the day's hours, so a lit square at night is fine when it is dry.
- **Selection:** the LLM sees each day's weather and which candidates are outdoor, and may pick at most as many outdoor places as the dry share of the hours the day is out allows. A guard enforces it: the least important outdoor picks give their slot to the best-ranked indoor candidates left, which come from the same interest- and distance-ranked pool. Must-visit places are never swapped, and every swap is listed (`weather_swaps`).
- **Routing** (soft time windows): the plan is made for travel time as before, then an outdoor visit costs up to 45 more minutes of travel for its share of bad minutes. Days are matched to the dates that suit them, each day is reordered, and outdoor stops caught in bad weather move to another day, alone or in exchange for an indoor stop, while that pays off. Days keep to their time budget, and dry, light days keep the plain plan. On random trips, outdoor visits meet 80–100% less bad weather for 5–20% more travel.
- **Replacing stops** fetches the latest forecast for the day; the LLM sees it and the day is ordered around it.

Limits: days never pause for rain to pass; and the forecast's 3-hour steps blur the exact hour a shower starts.

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
