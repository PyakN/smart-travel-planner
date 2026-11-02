# Smart AI Travel Planner

A travel planner with a two-layer architecture:

1. **LLM** (Gemini / OpenAI) parses the user's request and selects interesting places from our database.
2. **Geo-optimizer** (TSP / PostGIS) reorders those places into the shortest walking route, with no zigzags.

Stack: FastAPI · PostgreSQL + PostGIS · Next.js + Leaflet. Roadmap: [PROJECT_PLAN.md](PROJECT_PLAN.md). Dev rules: [CLAUDE.md](CLAUDE.md).

## Demo

**Live:** https://smart-travel-planner-liard.vercel.app, for example [a 2-day plan of Lisbon](https://smart-travel-planner-liard.vercel.app/?plan=18). The API runs on a free plan that sleeps when idle, so the first request after a quiet spell can take about a minute ([Render and Vercel](#render-and-vercel)).

![Day 2 of the plan: Torre de Belém, the Padrão dos Descobrimentos, the Jerónimos and the MAAT on foot, then rides to the Museu Nacional de Arte Antiga and the Gulbenkian](docs/screenshots/plan.webp)

<p>
  <img src="docs/screenshots/planner.webp" alt="The planner: choose a city, describe the trip in your own words, and a benchmark of the optimizer's route against the AI's own order" height="400">
  <img src="docs/screenshots/phone.webp" alt="Day 1 on a phone: the castle, the Baixa and Alfama on foot" height="400">
</p>

## Layout

```
backend/    FastAPI app (Python 3.12+)
frontend/   Next.js app with a Leaflet map
osrm/       Self-hosted walking routes (an OSRM image for the cities' areas)
deploy/     The production stack's edge (Caddyfile); the stack is docker-compose.prod.yml
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
python -m app.ingest berlin        # ~19.7k places (13k to eat and drink)
python -m app.ingest.enrich berlin
python -m app.ingest barcelona     # ~11.3k places (8.5k to eat and drink)
python -m app.ingest.enrich barcelona

# 5. Frontend
cd ../frontend
npm ci

# 6. Git hooks (run from the repo root)
cd ..
pre-commit install
```

Run it: start the API (`cd backend && uvicorn app.main:app --reload`) and the UI (`cd frontend && npm run dev`), then open http://localhost:3000. The UI proxies `/api/*` to the backend; see [frontend/README.md](frontend/README.md).

The importer caches the raw Overpass response in `backend/data/raw/`. Re-runs use the cache and upsert by OSM id; pass `--refresh` to fetch fresh data. An answer Overpass cut short (it ran out of time or memory) counts as a failure, so it is never cached.

**Cities:** Lisbon, Berlin and Barcelona, each with its bounding box, time zone and country (for public holidays in opening hours) in `app/ingest/cities.py`; `GET /cities` lists them. A plan is for the city its text names, or the one in `city` (`POST /plan`). Holidays are national only: Berlin's and Catalonia's own are not known. Places that OSM marks as closed in their name or hours ("(geschlossen)", "Cerrado permanentemente") are skipped in English, Portuguese, German, Spanish and Catalan. In the frontend the traveller chooses the city (each with its local time); the map, the clock and dates, the place search and the example requests follow it, and the plan request sends it as `city`. A request text that names another city gets a warning with a one-click switch before planning (the backend would refuse it with a 422). Changing the city clears the start point and must-visit places, which belong to the old city, with an Undo. Shared plans and saved trips open in their own city; `?city=<slug>` links to a city, and the last city chosen is remembered on the device.

`app.ingest.enrich` adds what the stop cards show: a photo from Wikimedia Commons (thumbnail, author and licence), and a short description from English Wikipedia or Wikidata. Opening hours and websites come from the OSM tags. It also counts how many Wikipedia languages cover each place (`wikipedia_languages`), the fame that ranks candidates (see [LLM layer](#llm-layer)). Its answers are cached in `backend/data/raw/<city>-wiki.json` (`--refresh` asks again; answers cached before the count existed are asked again by themselves). Places with a photo, with a description and in some Wikipedia: Lisbon 644, 451 and 422; Berlin 3,070, 2,943 and 1,399; Barcelona 859, 561 and 686.

## API

```bash
cd backend
uvicorn app.main:app --reload      # http://localhost:8000/docs for interactive docs
```

| Endpoint | Description |
|---|---|
| `GET /health` | Service, database and LLM status (`llm`: `ok`, `unavailable` while it is [not called after failures](#when-the-llm-is-down), or `not_configured`) |
| `GET /cities` | Supported cities: `slug`, `name`, `timezone` (IANA) and `bbox` (west, south, east, north) |
| `GET /places` | Search: `q` (name contains, accents ignored), `city`, `category` (repeatable), `bbox=west,south,east,north`, or `lat`+`lon`+`radius_m` (sorted by distance); `limit` / `offset` |
| `GET /places/{id}` | One place |
| `GET /categories` | Categories with place counts (optional `city`) |
| `POST /plan` | **Plan a trip from text**: `{"text", "city"?: slug, "start"?: {"lat", "lon", "round_trip"}, "must_visit"?: [place ids], "modes"?: ["walk", "transit"], "start_date"?: "YYYY-MM-DD", "weather_aware"?: bool, "day_start"?: "HH:MM", "day_end"?: "HH:MM", "first_day_start"?: "HH:MM", "day_count"?: 1-7, "day_hours"?: [{"start", "end"}]}` → dated days with their hours, ordered, timed stops (photo, description, personal note, opening hours, free time before them, forecast), when a free evening begins (`free_from`), how a round trip gets back to the start (`return_mode`) and map geometry. Saved; returns `id` |
| `GET /plans/{id}` | A saved plan |
| `GET /plans/{id}/gpx` | **The plan as a GPX file** (`?day=` for one day): see [Export](#export) |
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
| `POST /trips/{id}/edit` | **Edit a day of a trip** (no AI): `{"day", "remove"?: [place ids], "add"?: [place ids], "next"?: place id, "after"?: a stop of the day, "start"?: {"lat", "lon"}, "stay_min"?}` → a draft: a new plan version the trip uses once `PATCH` saves it, with an `edit` listing what was removed, added and dropped (and why) |
| `POST /trips/{id}/replace` | **Replace stops of a day of a trip** (AI): `{"day", "place_ids"}`, as `POST /plans/{id}/replace` does for its current version, but visited stops cannot be replaced and stay first, as they were → a draft, as an edit makes |
| `GET /venues` | **Places to eat and drink** near `lat`+`lon` within `radius_m` (250–2000, default 500): `kind` (`food` or `drinks`), `cuisine`, `vegetarian`, `vegan`, `open_now`, `outdoor_seating`, `limit`, `at` (when you set off, in the city's time: `YYYY-MM-DDTHH:MM`; default now); closest first, with the cuisines in range |

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
- **On a saved trip** (`POST /trips/{id}/replace`), visited stops cannot be replaced: they stay first, in their planned order, as they were, and the rest of the day is planned again after them, as a [day edit](#editing-a-saved-day) does (until the end of the day's hours plus 30 minutes, and every dropped stop says why). The answer is a draft.
- **Last resort:** a day left sparse (fewer stops, or an hour shorter) gets nearby fillers, and a one-note day (one kind of place is over half of 4+ stops) swaps one unticked stop of that kind. Visited and must-visit stops and the new replacements are never touched, and every adjustment is reported.

Error statuses:
- **401:** not logged in (`/auth/me` and `/trips`).
- **404:** no such plan, or a trip that does not exist or belongs to someone else.
- **409:** an email that has an account; a trip version that leaves out a visited place, or a draft made from an outdated version.
- **422:** the request can't be planned, for example an unsupported city, or a text that names another city than `city`.
- **429:** too many requests to the AI planner from this client (see [Rate limits](#rate-limits-and-llm-abuse)).
- **503:** the LLM is not configured. When it fails, plans are [made without it](#when-the-llm-is-down).
- **504:** planning timed out.

## Export

A plan leaves the app two ways, from the Export button next to the share link:

- **GPX** (`GET /plans/{id}/gpx`, `?day=N` for one day): a GPX 1.1 file for Organic Maps, OsmAnd, Komoot and GPS devices, checked against the official schema. Every stop is a waypoint named by day and stop ("2.3 Torre de Belém"), with its arrival time (UTC, as GPX keeps it; past midnight on the next date), the visit, the AI's note, the description, the website and the category; the start point is one too. Every day is a track, one segment per walk or ride, along the same street-following and transit geometry the map draws. Plans are public, so their files are too.
- **Google Maps** (the selected day, built in the browser): directions through the day's stops in their order, from the start point and back to it on round trips. Google Maps takes one way of travelling per route and at most 9 waypoints, and cannot ride through stops, so walks in a row are one route (longer ones in parts of about the same length) and each ride is a route of its own (`travelmode=transit`, `return_mode` for the way back). On a saved trip with visited stops, it goes from where the traveller is (Google Maps' own location) through the stops left.

## Accounts and saved trips

Plans are public: anyone with a plan's link can read it (`GET /plans/{id}`, the frontend's `?plan=<id>`). Accounts add private trips on top.

- **Accounts:** `users` keep an email (lowercase: log-ins ignore case), an argon2id password hash and a display name. Logging in starts a session: a random token in an HttpOnly, SameSite=Lax cookie with `Path=/`, which the browser sends through the frontend's same-origin `/api` proxy. The `sessions` table keeps only the token's SHA-256 and an expiry (30 days, `SESSION_DAYS`). Set `SESSION_COOKIE_SECURE=true` wherever the site is served over HTTPS. Password reset waits for an email sender.
- **Failed log-ins:** at most 5 per email in 15 minutes, then 429 with `Retry-After`, even with the right password. Every attempt counts until its password checks out, so guesses sent at once cannot slip past. The count is kept in memory, per process.
- **Saved trips:** a trip (`trips`) is a user's plan, by its current version. Replacing stops makes a new plan version that names the one it came from (`parent_id`); versions that go back to the same first plan are versions of the same trip, and `PATCH /trips/{id}` switches between them (save a new version, undo). Other users' trips answer 404.
- **Visited places** (`trip_visits`) live on the trip, not on a version: there is one record of them, and switching to a version that leaves a visited place out is refused (409).
- **Drafts:** changing a saved trip (a day edit, or replacing stops) makes a new version the trip does not use until `PATCH /trips/{id}` saves it. Only a draft made from the trip's current version can be saved: one made before another change was saved (another tab) is refused with 409. Undo switches back to a version the current one was made from.

The frontend has log-in and sign-up pages, My trips (rename, delete, delete the account), "Save to my trips" on a plan (logged out: log in or sign up first, then it saves), `?trip=<id>` for a saved trip, and a "Visited" tick on its stop cards. On a saved trip, "Edit day" takes stops out and adds places (the must-visit place search), and replacing stops keeps the visited ones first; either opens a draft on the map and in the plan, with a bar that lists the stops it drops and why. Save changes asks first when it drops stops; Discard keeps the trip as it was; Undo goes back after saving.

### Editing a saved day

`POST /trips/{id}/edit` changes one day as the trip goes, with the optimizer only (no LLM, about a second with OSRM):

- **Visited stops stay first**, in their planned order, as they were.
- **Where the rest begins:** with `start` (the traveller's location), from there: from now on when the day is under way, else from where the visited stops end. Without it, from the last visited stop, or as the day begins. A day whose hours are over cannot be planned from now (422).
- **`next`** (a stop of the day, or a place to add) is visited first, or right after `after`, a stop of the day: the day stays as planned up to that stop, then `next`. The other stops are reordered from it. The day keeps its end: back at the hotel on round trips, else open. A place to eat or drink chosen as the next stop is visited when you get there, not held to the hours its kind usually keeps (dinner and bars from 20:00), nor to its own opening hours (the draft warns instead, see below).
- **Stays:** `stay_min` sets how long to stay at the added places and the next stop (5 min to 8 h; by default the usual visit of their kind). Chosen stays stay with the plan in later edits.
- **When stops drop:** the pace no longer limits the day, only its end time plus 30 minutes. Beyond that, or when a place would be reached closed or dark, the least important stop goes, but only one whose leaving makes the day shorter (an afternoon sight stays when the evening runs long). Visited, must-visit, added and next stops never drop, nor the stops before the next one; when they alone run long, the draft warns instead.
- **Every dropped stop says why** in `edit.dropped`: "The day would end at 23:10 instead of 21:30." or "It would be closed, or dark, by the time you get there."
- **Opening hours:** stops keep their own (see [Day hours and evenings](#day-hours-and-evenings)), but for the next stop. Those of the places chosen in the edit are also checked against their visits: the draft warns when one is closed when you get there, or closes before you leave ("By its opening hours, Corner Pub is closed at 15:35.").
- A stop whose way starts at the traveller's location has a `departure` (where and when); the map draws nothing between the last visited stop and there.

The frontend's "Edit day" takes stops out and adds places; the traveller's location and the next stop come from the search for places to eat and drink.

### Places to eat and drink

`GET /venues` searches the city's places to eat and drink near a point (`ST_DWithin` on the GIST index, ~100 ms for the 2,100 venues within 2 km of Rossio):

- **Data:** every named venue in OpenStreetMap: restaurants and fast food (`restaurant`), cafés, ice cream and pastry shops (`cafe`), bars, pubs, clubs and music venues (`nightlife`), skipping those whose name or opening hours say they closed. In Lisbon: 3,167, 1,392 and ~400. Their cuisine, `diet:*`, `opening_hours` and `outdoor_seating` tags come along. OSM has no ratings or prices.
- **Opening hours** are read with [opening-hours-py](https://pypi.org/project/opening-hours-py/), in the city's time and with its public holidays: each venue is open, closed or unknown now (or at `at`, when you set off on a day ahead) and when you walk there, and says when that changes (within a day). About 3% of Lisbon's hours are written as prose: they count as unknown, like venues without hours.
- **Filters:** `kind` (`food`: restaurants and cafés; `drinks`: bars and nightlife), `cuisine` (an OSM value, e.g. `portuguese`), `vegetarian` (vegan places count), `vegan`, `open_now` (open by the time you walk there; unknown hours do not count) and `outdoor_seating`. The page lists the cuisines in range that the other filters leave, most common first.
- **Order:** by the minute of walking (straight line × 1.3 at 4 km/h), then the venues with the most complete data (hours, cuisine, diets, seating, website, phone), then distance.
- **Each venue** has its kind (`venue_type`), cuisines, diets (`"only"` for a vegetarian restaurant), outdoor seating, opening hours with `open_now`, `open_on_arrival` and `changes_at`, distance, walk and a usual stay (`stay_min`: café 30 min, bar 60, restaurant 75).

In the frontend, "Find places to eat" on a saved day turns the sidebar into the search (`?trip=<id>&eat=1`), with the route still on the map: near your location ("Use my location"), a pin on the map, or by default the day's last visited stop. Results are cards and markers; "← Back to route", the browser's Back and Esc leave it. A free evening links to the search around the day's last stop. **Add to route** asks how long to stay and where in the day, and edits the day through `POST /trips/{id}/edit` with the venue as `next`: it is the next stop after where the search is. On a day under way, around where you are (your location, a pin, the stop you visited last, the hotel before any visit), it goes next from there, now (`start`: then the rest, back to the hotel). Otherwise it goes right after the stop searched around (`after`), or after the stop (or the hotel) nearest the pin: the day stays as planned up to there, and the rest is planned again from the venue. "Visit" offers the other places in the day ("After Castelo · 12:15"). On a day ahead, the search tells whether venues are open when you would set off for them (`at`: "Open or closed as of 12:15, when you leave Castelo"), not now. The draft opens on the route, with the approval step for any stops it drops.

## LLM layer

The LLM never invents places. A request goes through four steps:

1. **Parse:** the request text becomes a `TripRequest` (city, days, interests, avoid, pace, keywords).
2. **Candidates:** SQL ranks the city's sights by fame, interests and keywords, plus closeness to the hotel and the must-visit places (PostGIS distance; full weight at the anchor, none beyond 2.5 km on foot or 5 km with transit). Fame grows with the log of the Wikipedia languages that cover a place (1 gives 0.6, 30 give 3, 100 give the full 4), so a world-famous place outranks an obscure match for the interests, and a known match outranks it. One place stands for each Wikidata item (OSM maps some sights in pieces: 24 of Lisbon's aqueduct). The interests are a guess at categories (the Sagrada Família is a church on a Gaudí day), so the city's most famous places, a third of the pool's size, always join it, and they lead the list the LLM sees. Food and drink venues are never candidates.
3. **Select:** the LLM fills the slots the must-visit places leave, picking ids from that candidate list (it sees the distances), and writes a one-sentence note per place on why it suits the traveller.
4. **Guard:** a deterministic check drops any id that isn't a candidate, and places with the same name as one already chosen (OSM maps some sights twice).

When the LLM is unavailable, rules read the request and the best-ranked candidates are chosen: see [When the LLM is down](#when-the-llm-is-down).

Configure it in `.env`: `LLM_PROVIDER`, the matching API key, and optionally `LLM_MODEL` and `LLM_FALLBACK_MODEL`. For real public transport routes, also set `HERE_API_KEY` (see [Route optimizer](#route-optimizer)); for the weather, `OPENWEATHER_API_KEY` (see [Weather](#weather)).

```bash
cd backend
python evals/selection_eval.py     # live eval against the real LLM + DB (costs a few cents)
```

## Route optimizer

`app/optimizer/` turns the selected places into days and walking order:

- **Distances:** an OSRM foot routing matrix, falling back to haversine × 1.3. Set `ROUTING_PROVIDER` to choose. `OSRM_BASE_URL` is the public FOSSGIS server by default, which took about 10 s for most 25-point tables when measured (its 10 s timeout then falls back to straight lines). The self-hosted one in `osrm/` answers them in 50–300 ms: `docker compose --profile osrm up -d` (the first build downloads ~900 MB from Geofabrik and takes ~15 min), then `OSRM_BASE_URL=http://localhost:5000`. It knows only the areas in `osrm/areas.txt` (each city's bbox plus 3–5 km; a test keeps them in step with the cities), and a point that OSRM moves more than 1 km to reach a street falls back to haversine, rather than being measured from somewhere else.
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

`day_count` (the form's Days, "As described" by default) sets the number of days in place of
the one the text gives. `day_hours` gives each day its own hours instead, day 1 first, one per
day (the form's "Different hours each day", offered from 2 days on): a 10:00–18:00 Friday, a
13:00–23:30 Saturday and a short Sunday. A day may run past midnight, but not past the start of
the next one.

- **The pace is a share of the hours:** relaxed ½, moderate ⅔, intense ⅚ of them go to
  travel and visits, the rest to meals and rest. The default day plans exactly as before (8 h
  of a 12 h day at a moderate pace); a day from 16:00 to 21:30 gets 3 h 40 min and 3 places
  instead of 6.
- **When places can be visited** (`app/catalog.py`, `hours` on every stop): indoor sights
  and cafés are open by day, until 20:00 (`day`), outdoor sights need daylight
  (`daylight`), bars, pubs, clubs, fado houses and restaurants open at 20:00 (`night`;
  planned only when you choose them, and visited at once as the next stop of a day edit),
  and lit squares and places whose OSM opening hours run past 22:00 suit both (`any`).
  Sunrise and sunset come from the sunrise equation for every trip day (`app/sun.py`), or
  from the forecast on weather-aware plans.
- **Opening hours of their own** (`app/osm_hours.py`): a place's OSM `opening_hours` are
  read for the date of every trip day, and replace the hours of its kind: a museum closes
  when it closes (Torre de Belém at 17:30 in winter, and not at all on Mondays), a visit
  waits out a lunch break, and the castle stays open until 21:00. Outdoor sights still need
  daylight with them, and evening places the evening. Hours that cannot be read, or say
  `unknown`, leave a place to the hours of its kind. Places closed on every day of the trip
  are no candidates, and replacements must be open on the day's date.
- **Routing with time windows:** a visit that comes early waits for the place to open (the
  stop's `wait_min`, shown as free time), and none may run past closing time or sunset:
  a day that breaks that is reordered, else its least important stop with such hours is
  dropped (places that cannot be visited that day at all first, and only those whose
  leaving makes the day less late) and the plan says so, unless another day of the trip is
  open for it: then it goes there, in place of less important stops if need be. Days must
  also end by the end of their hours; days with shorter hours get fewer stops.
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

Limits: places without opening hours in OSM keep the hours of their kind, so an indoor sight
closes at 20:00 and opens whenever the day starts (169 of Lisbon's 2,230 sights have hours,
68 of its 105 museums among them); the LLM does not see which day of a trip a place is
closed on (the optimizer moves it); a day only waits for places to open, it never takes a
break in the middle.

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

## Reliability

### Logs and request ids

Every log line goes through one handler (`app/logs.py`), uvicorn's included: readable text by default, one JSON object per line with `LOG_FORMAT=json` (for a log collector); `LOG_LEVEL` sets the level (`INFO`).

- **Request ids:** every request gets an id, the caller's `X-Request-ID` when it is plain and up to 64 characters (a proxy's), else a new one. Every line logged while the request runs carries it as `request_id`, and the response returns it in `X-Request-ID`: an error a user reports leads to its log lines.
- **One line per request** once it is answered: method, path, status, `duration_ms` and the client's address (`/health` only at `DEBUG`). uvicorn's own access log is off.
- **Events** carry their numbers as fields: each LLM answer (`model`, `input_tokens`, `output_tokens`, `duration_ms`), each plan made (`plan_id`, `city`, `days`, `stops`, `timings_ms`), and each outgoing HTTP call (httpx, API keys hidden).
- **Unexpected errors** answer 500 with the request id; the traceback is in the log.

```json
{"time": "2026-10-31T22:05:57.759+00:00", "level": "INFO", "logger": "app.requests", "message": "GET /cities 200", "request_id": "demo-1", "method": "GET", "path": "/cities", "status": 200, "duration_ms": 2, "client": "127.0.0.1"}
```

### Rate limits and LLM abuse

The endpoints that call the LLM (`POST /plan`, `POST /plans/{id}/replace`, `POST /trips/{id}/replace`) cost tokens and seconds, so each client gets a share:

- **Per client:** at most 5 requests a minute and 100 a day (`AI_REQUESTS_PER_MINUTE`, `AI_REQUESTS_PER_DAY`; 0 turns one off), then 429 with `Retry-After` and "Try again in 40 s". Clients are told apart by address, in memory per process (`app/rate_limit.py`). Other endpoints are not limited; failed log-ins have [their own limit](#accounts-and-saved-trips).
- **For everyone:** a daily token budget (`LLM_DAILY_TOKEN_BUDGET`; once it is used up, plans are [made without the LLM](#when-the-llm-is-down)), and identical requests answered from a cache without calling the LLM.
- **Small requests:** the text is at most 1,000 characters, a trip at most 7 days and 10 must-visit places.
- **Nothing to steer:** the LLM only fills in a schema, a parsed request or a list of ids from the candidates with a short note each (validated by Pydantic, unknown ids dropped), so it cannot be used as a general chatbot, and a request that tries to instruct it can at most change which candidates it picks and how the notes read.

Behind a proxy, the client's address comes from `X-Forwarded-For`, which uvicorn trusts only from `FORWARDED_ALLOW_IPS` (127.0.0.1 by default). The Next.js proxy cannot name the client: it forwards the header the browser sent, unchanged, or none. So in production an edge sets the header and sends `/api/*` straight to the API, which trusts that edge only (see [Deployment](#deployment)); the token budget holds either way.

### When the LLM is down

- **Retries, then a fallback model:** a failed call (rate limit, server error, malformed answer, timeout) is retried with backoff (`LLM_MAX_RETRIES`), then tried on `LLM_FALLBACK_MODEL` if set.
- **A deadline:** one call ends within `LLM_DEADLINE_S` (40 s), retries included; a plan makes two calls and has 90 s.
- **A circuit breaker:** after 3 calls in a row that failed (`LLM_CIRCUIT_FAILURES`), the LLM is not called for 60 s (`LLM_CIRCUIT_COOLDOWN_S`): plans are made without it at once instead of waiting out the retries. Then calls go through again, and the first success closes it. `GET /health` says `"llm": "unavailable"` meanwhile.
- **Plans without the AI:** when the LLM fails anyway (down, the token budget used up, or it refuses), the plan is still made, without it (`app/services/ai_fallback.py`). Rules read the request: the city it names, its days ("2 days", "a weekend", "48 hours"), interests and what to avoid ("museums, no churches"), the pace ("with kids" is relaxed) and the names it gives ("the Torre de Belém"). The places are the best-ranked candidates (fame, those interests and names, closeness to the hotel and the must-visit places), and the plan says so: `"ai_fallback": true` and a rationale ("The AI planner is unavailable right now, so this plan has the best-known places in Lisbon for the interests your request names, without a note on each. Try again later for a plan made for you."), which the frontend shows as a "Planned without the AI" notice. Replacing stops takes the best-ranked places that fit, and says so in `edit.warnings`. What only the LLM gives is missing: wishes in the traveller's own words, the notes on each place, and refusing a city we do not support (a text that names no supported city is planned for the chosen one, which the notice names).

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

cd frontend
npm test                           # unit tests (vitest)
npx playwright install chromium    # once
npm run test:e2e                   # end-to-end tests in a browser (needs the database)
```

The end-to-end tests run the real frontend and API on a database of their own, with a scripted LLM: see [frontend/README.md](frontend/README.md#end-to-end-tests).

## Deployment

The whole app runs on one host with Docker Compose (`docker-compose.prod.yml`), in six containers. Only the edge publishes ports:

```
browser -> edge (Caddy: TLS, X-Forwarded-For) -> /api/*: backend (uvicorn) -> db (PostGIS), osrm (walking routes)
                                              -> the rest: frontend (Next.js)
```

```bash
cp .env.example .env    # POSTGRES_PASSWORD (letters and digits: it goes into a URL), API keys, MAPBOX_MAP_KEY
docker compose -f docker-compose.prod.yml up -d --build   # the first build takes ~15 min (OSRM data)

# Places: import them in the stack...
docker compose -f docker-compose.prod.yml run --rm backend python -m app.ingest lisbon
docker compose -f docker-compose.prod.yml run --rm backend python -m app.ingest.enrich lisbon
# ...or copy them from the development database (the migrations create the categories)
docker exec travel-planner-db pg_dump -U planner -d travel_planner --data-only -Fc -t places > places.dump
docker compose -f docker-compose.prod.yml exec -T db pg_restore -U planner -d travel_planner --data-only --disable-triggers < places.dump

docker compose -f docker-compose.prod.yml logs -f backend   # JSON logs with request ids
```

- **Images:** `backend/Dockerfile` (python:3.12-slim, non-root; the `migrate` service runs `alembic upgrade head` with it before the API starts, and the importers run with it too), `frontend/Dockerfile` (a standalone Next.js server on node:24-alpine) and `osrm/Dockerfile` (see [Route optimizer](#route-optimizer)). Each also builds and runs alone; its header shows how.
- **HTTPS:** set `SITE_ADDRESS` to the domain name that points at the host, with ports 80 and 443 open: Caddy gets and renews the certificate. Then set `SESSION_COOKIE_SECURE=true`. The default, `:80`, serves plain HTTP (`HTTP_PORT` and `HTTPS_PORT` move the published ports).
- **Map tiles:** `MAPBOX_MAP_KEY`, a public Mapbox token, goes into the frontend build as `NEXT_PUBLIC_MAPBOX_TOKEN`, so changing it needs `--build`. Restrict the token to the site's URLs in the Mapbox account: every visitor's browser sees it. Without it, the map uses the public OpenStreetMap tiles, which are not meant for real traffic.
- **Client addresses** (for the [per-client limits](#rate-limits-and-llm-abuse)): Caddy sets `X-Forwarded-For` to the address a request came from, ignoring any the client sent, and sends `/api/*` straight to uvicorn. uvicorn takes that header from Caddy's fixed address only (`FORWARDED_ALLOW_IPS=10.201.0.10`). Checked on the stack: a request claiming `X-Forwarded-For: 6.6.6.6` is logged with its real address, and of six plan requests each claiming another address, the sixth gets a 429. Behind a load balancer or CDN, list its addresses in Caddy's `trusted_proxies`. The limits live in memory per process, so the API runs as one process.

### Render and Vercel

The other way to deploy: the frontend on Vercel, the API on Render, the database on Neon.

```
browser -> Vercel (Next.js; /api/* proxied with X-Forwarded-For and X-Origin-Secret) -> Render (API) -> Neon (PostGIS)
```

1. **Database, once:** the migrations and the places, from this machine. The Neon URL is the direct host (not `-pooler`), as `postgresql+asyncpg://USER:PASSWORD@HOST/DBNAME?ssl=require` for the app; `pg_restore` takes the plain `postgresql://…?sslmode=require` form.
   ```bash
   cd backend
   DATABASE_URL="postgresql+asyncpg://USER:PASSWORD@HOST/DBNAME?ssl=require" alembic upgrade head
   docker exec travel-planner-db pg_dump -U planner -d travel_planner --data-only -Fc -t places > places.dump
   docker exec -i travel-planner-db pg_restore --data-only --no-owner -d "postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require" < places.dump
   ```
2. **API on Render:** New > Blueprint with this repository. `render.yaml` sets up a Docker service on the free plan in Frankfurt (next to Neon's `eu-central-1`), checked at `/health`, deployed once a commit's CI passes. It asks for `DATABASE_URL`, the API keys and `ORIGIN_SECRET` (`python -c "import secrets; print(secrets.token_hex(32))"`). The image runs the migrations as it starts (`MIGRATE_ON_START`) and listens on Render's `PORT`. By hand instead: a Docker web service with Dockerfile Path `backend/Dockerfile`, Docker Build Context Directory `backend` and no Root Directory (with one, Render takes both paths from it), region Frankfurt, health check `/health`, and the environment `render.yaml` lists. A deploy that ran before those settings were saved fails with `open Dockerfile: no such file or directory`: deploy again from Manual Deploy.
3. **Frontend on Vercel** (root directory `frontend`): `BACKEND_URL` (the API's URL as Render shows it), `ORIGIN_SECRET` (the same value) and `NEXT_PUBLIC_MAPBOX_TOKEN`. Redeploy after changing them: `BACKEND_URL` and `NEXT_PUBLIC_*` are fixed at build time.
4. **Check:** the API's `/health` answers `ok`, its `/cities` answers 403 (it only answers the website), and the site plans a trip.

- **Client addresses:** Vercel sets `X-Forwarded-For` to the visitor's address and Render's proxy adds its own after it, so the API takes the first one (`FORWARDED_ALLOW_IPS=*`). A caller who skips Vercel could claim any address there, so with `ORIGIN_SECRET` set the API answers only requests that carry it in `X-Origin-Secret`, which `frontend/src/proxy.ts` adds (403 otherwise; `/health` stays open for Render's checks).
- **Neon suspends** after a few idle minutes and closes the API's connections: each one is checked before use (`pool_pre_ping`), so the next request does not fail.
- **Free plans:** Render stops the API after 15 idle minutes and takes about a minute to start it (Vercel waits up to 120 s); the limits, the daily token budget and the caches live in memory and start afresh then. Walking distances come from the public OSRM server unless `OSRM_BASE_URL` points at a self-hosted one; a free Render instance cannot build it (it needs ~1.2 GB of RAM).

## Secrets

Never commit `.env`. Only `.env.example` lives in git.

- **Every commit:** pre-commit runs gitleaks on what is being committed, blocks `.env` files and private keys.
- **Every push and pull request:** CI's `secrets` job runs gitleaks over the whole history, every branch included. To run it locally: `gitleaks git --redact -v` (the binary pre-commit built is in `~/.cache/pre-commit/*/golangenv-default/bin/`).
- **At run time:** keys come from the environment only, as `SecretStr` (hidden in reprs and errors); the keys HERE and OpenWeatherMap take in the query string are masked in logged URLs (`app/http_logging.py`), and request logs carry the path only.
- **Checked on 2026-10-31:** gitleaks found nothing in the 167 commits of every branch; the only env files ever committed are the two `.env.example`; no Google, OpenAI, HERE or OpenWeatherMap key pattern appears anywhere in the history, and the test fixtures hold no keys.

If a secret lands in a commit anyway, treat it as compromised: rotate the key first, then clean the history.
