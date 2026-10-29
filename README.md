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
python -m app.ingest lisbon        # ~7.2k places from OpenStreetMap (5k to eat and drink), ~1 min
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
| `POST /plan` | **Plan a trip from text**: `{"text", "start"?: {"lat", "lon", "round_trip"}, "must_visit"?: [place ids], "modes"?: ["walk", "transit"], "start_date"?: "YYYY-MM-DD", "weather_aware"?: bool, "day_start"?: "HH:MM", "day_end"?: "HH:MM", "first_day_start"?: "HH:MM"}` → dated days with their hours, ordered, timed stops (photo, description, personal note, opening hours, free time before them, forecast), when a free evening begins (`free_from`) and map geometry. Saved; returns `id` |
| `GET /plans/{id}` | A saved plan |
| `POST /plans/{id}/replace` | **Replace stops of a day**: `{"day", "place_ids"}` → a new saved version (`parent_id` = this plan), with an `edit` listing what was replaced, added, adjusted and dropped |
| `POST /auth/signup` | Create an account and log in: `{"email", "password", "display_name"}` (password 8+ characters); 409 if the email has an account |
| `POST /auth/login` | Log in: `{"email", "password"}`; 401 on a wrong email or password, 429 after 5 failed log-ins in 15 minutes |
| `POST /auth/logout` | End this session |
| `GET /auth/me` · `DELETE /auth/me` | The logged-in user (401 if none) · delete the account and its trips |
| `POST /trips` | **Save a plan** to my trips: `{"plan_id", "title"?}`; a plan saved already gives that trip (200) |
| `GET /trips` | My trips, the most recently changed first |
| `GET /trips/{id}` | A trip with its current plan and visited places |
| `PATCH /trips/{id}` | Rename (`{"title"}`) or switch to another version of its plan (`{"plan_id"}`: a draft made from its current version to save it, or a version the current one was made from to undo); 409 for a draft made from an outdated version |
| `DELETE /trips/{id}` | Delete a trip (its plans stay readable by their links) |
| `PUT` · `DELETE /trips/{id}/visits/{place_id}` | Tick a stop of the trip's current plan visited · untick it |
| `POST /trips/{id}/edit` | **Edit a day of a trip** (no AI): `{"day", "remove"?: [place ids], "add"?: [place ids], "next"?: place id, "start"?: {"lat", "lon"}, "stay_min"?}` → a draft: a new plan version the trip uses once `PATCH` saves it, with an `edit` listing what was removed, added and dropped (and why) |
| `GET /venues` | **Places to eat and drink** near `lat`+`lon` within `radius_m` (250–2000, default 500): `kind` (`food` or `drinks`), `cuisine`, `vegetarian`, `vegan`, `open_now`, `outdoor_seating`, `limit`; closest first, with the cuisines in range |

Example: museums and viewpoints within 400 m of Praça do Comércio:

```
GET /places?lat=38.7075&lon=-9.1364&radius_m=400&category=museum&category=viewpoint
```

Plan a trip (needs an LLM key in `.env`):

```bash
curl -X POST localhost:8000/plan -H "Content-Type: application/json" \
  -d '{"text": "2 days in Lisbon: viewpoints, the castle and Belém", "start": {"lat": 38.7139, "lon": -9.1394}}'
```

Plans suggest sights only: never restaurants, cafés, bars, pubs, clubs or fado houses, even when the request names them (a request that asks for food or nightlife gets a note saying so). On a saved trip, [find places to eat and drink](#places-to-eat-and-drink) near your stops and add them to the day; or add the ones you want as must-visit places: they are planned when they open, dinner and bars from 20:00.

Must-visit places are ids from `GET /places?q=...`. They always get a slot on some day if they fit its time budget: trimmed only after every optional stop, and moved to another day when their own day overflows. `modes`: walking only rides nothing, transit only rides every leg over 1 km, both (the default) ride legs over 2.5 km.

Replacing stops (`POST /plans/{id}/replace`):
- The ticked stops leave the day. Nothing planned on any day, or rejected in an earlier swap of the plan, comes back.
- Candidates are ranked around the stops that stay and must fit the freed time; they are sights only, as in new plans. The LLM picks the replacements by id.
- Only that day is re-optimized; the other days are copied unchanged.
- **Last resort:** a day left sparse (fewer stops, or an hour shorter) gets nearby fillers, and a one-note day (one kind of place is over half of 4+ stops) swaps one unticked stop of that kind. Must-visit stops and the new replacements are never touched, and every adjustment is reported.

Error statuses:
- **401:** not logged in (`/auth/me` and `/trips`).
- **404:** no such plan, or a trip that does not exist or belongs to someone else.
- **409:** an email that has an account; a trip version that leaves out a visited place, or a draft made from an outdated version.
- **422:** the request can't be planned, for example an unsupported city.
- **429:** the daily LLM token budget is used up.
- **502:** the LLM rejected the request.
- **503:** the LLM is unavailable or not configured.
- **504:** planning timed out.

## Accounts and saved trips

Plans are public: anyone with a plan's link can read it (`GET /plans/{id}`, the frontend's `?plan=<id>`). Accounts add private trips on top.

- **Accounts:** `users` keep an email (lowercase: log-ins ignore case), an argon2id password hash and a display name. Logging in starts a session: a random token in an HttpOnly, SameSite=Lax cookie with `Path=/`, which the browser sends through the frontend's same-origin `/api` proxy. The `sessions` table keeps only the token's SHA-256 and an expiry (30 days, `SESSION_DAYS`). Set `SESSION_COOKIE_SECURE=true` wherever the site is served over HTTPS. Password reset waits for an email sender.
- **Failed log-ins:** at most 5 per email in 15 minutes, then 429 with `Retry-After`, even with the right password. Every attempt counts until its password checks out, so guesses sent at once cannot slip past. The count is kept in memory, per process.
- **Saved trips:** a trip (`trips`) is a user's plan, by its current version. Replacing stops makes a new plan version that names the one it came from (`parent_id`); versions that go back to the same first plan are versions of the same trip, and `PATCH /trips/{id}` switches between them (save a new version, undo). Other users' trips answer 404.
- **Visited places** (`trip_visits`) live on the trip, not on a version: there is one record of them, and switching to a version that leaves a visited place out is refused (409).
- **Drafts:** changing a saved trip (a day edit, or replacing stops) makes a new version the trip does not use until `PATCH /trips/{id}` saves it. Only a draft made from the trip's current version can be saved: one made before another change was saved (another tab) is refused with 409. Undo switches back to a version the current one was made from.

The frontend has log-in and sign-up pages, My trips (rename, delete, delete the account), "Save to my trips" on a plan (logged out: log in or sign up first, then it saves), `?trip=<id>` for a saved trip, and a "Visited" tick on its stop cards. On a saved trip, "Edit day" takes stops out and adds places (the must-visit place search), and replacing stops works as before; either opens a draft on the map and in the plan, with a bar that lists the stops it drops and why. Save changes asks first when it drops stops; Discard keeps the trip as it was; Undo goes back after saving.

### Editing a saved day

`POST /trips/{id}/edit` changes one day as the trip goes, with the optimizer only (no LLM, about a second with OSRM):

- **Visited stops stay first**, in their planned order, as they were.
- **Where the rest begins:** with `start` (the traveller's location), from there: from now on when the day is under way, else from where the visited stops end. Without it, from the last visited stop, or as the day begins. A day whose hours are over cannot be planned from now (422).
- **`next`** (a stop of the day, or a place to add) is visited first; the other stops are reordered from it. The day keeps its end: back at the hotel on round trips, else open. A place to eat or drink chosen as the next stop is visited when you get there, not held to the hours its kind usually keeps (dinner and bars from 20:00).
- **Stays:** `stay_min` sets how long to stay at the added places and the next stop (5 min to 8 h; by default the usual visit of their kind). Chosen stays stay with the plan in later edits.
- **When stops drop:** the pace no longer limits the day, only its end time plus 30 minutes. Beyond that, or when a place would be reached closed or dark, the least important stop goes, but only one whose leaving makes the day shorter (an afternoon sight stays when the evening runs long). Visited, must-visit, added and next stops never drop; when they alone run long, the draft warns instead.
- **Every dropped stop says why** in `edit.dropped`: "The day would end at 23:10 instead of 21:30." or "It would be closed, or dark, by the time you get there."
- **Opening hours** of the places chosen in the edit (OSM `opening_hours`) are checked against their visits: the draft warns when one is closed when you get there, or closes before you leave ("By its opening hours, Corner Pub is closed at 15:35.").
- A stop whose way starts at the traveller's location has a `departure` (where and when); the map draws nothing between the last visited stop and there.

The frontend's "Edit day" takes stops out and adds places; the traveller's location and the next stop come from the search for places to eat and drink.

### Places to eat and drink

`GET /venues` searches the city's places to eat and drink near a point (`ST_DWithin` on the GIST index, ~100 ms for the 2,100 venues within 2 km of Rossio):

- **Data:** every named venue in OpenStreetMap: restaurants and fast food (`restaurant`), cafés, ice cream and pastry shops (`cafe`), bars, pubs, clubs and music venues (`nightlife`), skipping those whose name or opening hours say they closed. In Lisbon: 3,167, 1,392 and ~400. Their cuisine, `diet:*`, `opening_hours` and `outdoor_seating` tags come along. OSM has no ratings or prices.
- **Opening hours** are read with [opening-hours-py](https://pypi.org/project/opening-hours-py/), in the city's time and with its public holidays: each venue is open, closed or unknown now and when you walk there, and says when that changes (within a day). About 3% of Lisbon's hours are written as prose: they count as unknown, like venues without hours.
- **Filters:** `kind` (`food`: restaurants and cafés; `drinks`: bars and nightlife), `cuisine` (an OSM value, e.g. `portuguese`), `vegetarian` (vegan places count), `vegan`, `open_now` (open by the time you walk there; unknown hours do not count) and `outdoor_seating`. The page lists the cuisines in range that the other filters leave, most common first.
- **Order:** by the minute of walking (straight line × 1.3 at 4 km/h), then the venues with the most complete data (hours, cuisine, diets, seating, website, phone), then distance.
- **Each venue** has its kind (`venue_type`), cuisines, diets (`"only"` for a vegetarian restaurant), outdoor seating, opening hours with `open_now`, `open_on_arrival` and `changes_at`, distance, walk and a usual stay (`stay_min`: café 30 min, bar 60, restaurant 75).

In the frontend, "Find places to eat" on a saved day turns the sidebar into the search (`?trip=<id>&eat=1`), with the route still on the map: near your location ("Use my location"), a pin on the map, or by default the day's last visited stop. Results are cards and markers; "← Back to route", the browser's Back and Esc leave it. A free evening links to the search around the day's last stop. **Add to route** asks how long to stay and edits the day through `POST /trips/{id}/edit`: on a day under way, with the pin as `start` and the venue as `next` (go there now, then the rest, back to the hotel); on another day, as a place added to it, which the optimizer fits in when it suits (restaurants and bars in the evening). The draft opens on the route, with the approval step for any stops it drops.

## LLM layer

The LLM never invents places. A request goes through four steps:

1. **Parse:** the request text becomes a `TripRequest` (city, days, interests, avoid, pace, keywords).
2. **Candidates:** SQL ranks the city's sights by notability, interests and keywords, plus closeness to the hotel and the must-visit places (PostGIS distance; full weight at the anchor, none beyond 2.5 km on foot or 5 km with transit). Food and drink venues are never candidates.
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
  and cafés close at 20:00 (`day`), outdoor sights need daylight (`daylight`), bars, pubs,
  clubs, fado houses and restaurants open at 20:00 (`night`; planned only when you choose
  them, and visited at once as the next stop of a day edit), and lit squares and places
  whose OSM opening hours run past 22:00 suit both (`any`). Sunrise and
  sunset come from the sunrise equation for every trip day (`app/sun.py`), or from the
  forecast on weather-aware plans.
- **Routing with time windows:** a visit that comes early waits for the place to open (the
  stop's `wait_min`, shown as free time), and none may run past closing time or sunset:
  a day that breaks that is reordered, else its least important stop with such hours is
  dropped (places that cannot be visited that day at all first) and the plan says so.
  Days must also end by the end of their hours; days with shorter hours get fewer stops.
- **Selection:** each day is split into what it holds before 20:00 (and how much of that
  is in daylight) and after. An evening holds at most 2 places, lit squares and sights open
  late (about 100 in Lisbon: squares, lit viewpoints, Mercado da Ribeira), which come in a
  pool of their own; the rest of it is free time. The LLM is told and sees when each
  candidate can be visited. A guard swaps picks the hours cannot take: outdoor sights
  beyond the daylight, places from the evening pool beyond the evening, and places closed
  at night beyond the time before 20:00. Swaps are listed in `hours_swaps`.
- **Free evening:** a day whose hours run past 20:00 and go on at least an hour after its
  last stop gets `free_from`, and the plan shows "Free time from 21:40 until 03:00" after
  that stop. A day from 16:00 to 03:00 has afternoon sights, a lit square or two, and a free
  evening.
- **Data:** `python -m app.ingest lisbon --refresh` imports named squares (`landmark`,
  ~90 in Lisbon) and every place to eat and drink (see
  [Places to eat and drink](#places-to-eat-and-drink)), which plans never suggest: they are
  there for the venue search and the must-visit search.

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
