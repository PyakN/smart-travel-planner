# Smart AI Travel Planner — Master Plan (MVP)

**Idea:** a two-layer architecture.
1. **LLM** (Gemini / OpenAI) parses the request and picks interesting places from our database.
2. **Optimizer** (TSP / PostGIS) reorders the places so the walking route is as short as possible, with no zigzags.

**Stack:** Python (FastAPI), PostgreSQL + PostGIS, Next.js + Leaflet (Mapbox GL later, optional).

**Key project metric:** how many kilometres the optimizer saves compared with the order the LLM suggested (plus the number of route self-intersections).

**Principles:**
- The LLM only parses and selects; coordinates and visiting order always come from the database and the algorithm.
- One city for the MVP; expand later.
- Every step = one small atomic commit.

---

## Phase 0. Repository skeleton
- [x] Monorepo layout: `backend/`, `frontend/`, `docs/`
- [x] `docker-compose.yml` with `postgis/postgis`
- [x] `.env.example` (DB_URL, LLM_PROVIDER, GEMINI_API_KEY, OPENAI_API_KEY)
- [x] Linters and formatters: ruff + mypy (backend); eslint + prettier for the frontend moved to Phase 6
- [x] pre-commit hooks (including a secret scan)
- [x] README with run commands

**DoD:** `docker compose up` starts an empty PostGIS; hooks work.

## Phase 1. Data and database schema
- [x] Extension `postgis` (`pgvector` deferred to Phase 3, only if embeddings are needed)
- [x] Tables: `places`, `categories`, `routes`, `route_stops`
- [x] Alembic migrations
- [x] `geography(Point, 4326)` column + GIST index
- [x] Pick the starting city: **Lisbon**
- [x] POI import script from OpenStreetMap (Overpass API): `python -m app.ingest lisbon`
- [x] Cleanup: duplicates, empty names, normalized categories/tags
- [ ] (optional) POI descriptions and embeddings for semantic search (moved to Phase 3)

**DoD:** the DB holds ≥ 500 meaningful POIs for one city; `ST_DWithin` queries are fast.
**Result:** 2,143 Lisbon POIs in 10 categories (632 with a Wikidata link); a 1 km `ST_DWithin` around Praça do Comércio uses the GIST index and runs in ~0.6 ms.

## Phase 2. Backend core
- [x] FastAPI skeleton, package layout (api / repositories / schemas; `services/` arrives with the LLM and optimizer logic)
- [x] Config via `pydantic-settings`
- [x] `GET /health`
- [x] Async DB access (SQLAlchemy 2 + asyncpg)
- [x] `GET /places` (filters: city, category, bbox, radius) + `GET /places/{id}`, `GET /categories`
- [x] Tests: pytest + DB in a container (testcontainers)
- [x] CI job: lint + tests (`.github/workflows/ci.yml`; first run happens once the repo is pushed)

**DoD:** tests are green; endpoints are documented at `/docs`.

## Phase 3. LLM layer
- [x] Provider abstraction (`LLMProvider` + `LLMService`) with Gemini and OpenAI implementations (OpenAI tested with mocks only so far)
- [x] Parse the request into structured JSON: `TripRequest {city, days, interests, avoid, pace, keywords, notes}` (structured output + Pydantic validation)
- [x] Candidate generation from the DB: notability + interest + accent-insensitive keyword ranking, avoided categories excluded
- [x] LLM picks POIs from the candidate list (by `id`, not by name)
- [x] Guard: unknown/duplicate ids are dropped and backfilled from the ranking
- [x] Retries with backoff, fallback model, timeouts, LRU response cache, daily token budget, request length cap
- [x] Tests with a mocked LLM + live eval prompts (`python evals/selection_eval.py`)
- [ ] (optional) Embeddings / pgvector for semantic matching: not needed so far, revisit if keyword matching falls short

**DoD:** a request text yields a list of valid `place_id`s in reasonable time.
**Result:** 5/5 eval cases pass on `gemini-3.5-flash-lite`, ~2 s and ~1–2.5k tokens per request (two LLM calls).

## Phase 4. Geo-optimization
- [x] Distance matrix: haversine (× 1.3 detour factor) as fallback
- [x] TSP solver: nearest neighbour + 2-opt + Or-opt (0.0% gap to OR-Tools on benchmark days)
- [x] Split into days: balanced k-means, route-first and selection-order splits limited by the time budget, plus relocation between days (in Python, not `ST_ClusterKMeans`: it needs capacities)
- [x] Starting point: optional hotel, open end or round trip (free start by default)
- [x] Real walking distances: OSRM foot profile (public FOSSGIS server), haversine fallback
- [x] OR-Tools for comparison (benchmark reference)
- [x] Constraints: visit duration per category, daily time budget per pace (least important stops dropped)
- [x] Constraints: opening hours (each place's OSM `opening_hours` on the trip's dates, see Phase 6d)
- [x] Benchmark: LLM order vs optimizer (km, self-intersections): see `docs/benchmark.md`
- [ ] (later) Swap moves / joint VRP for the remaining multi-day gap

**DoD:** on test sets the route is never longer than the baseline order; metrics recorded in `docs/benchmark.md`.
**Result:** −55% walking vs the selection order and −1% vs an LLM-made itinerary (13 → 0 crossings); never longer than the selection order (property-tested); optimizer ≤ 8 ms per trip.

## Phase 5. Planning API
- [x] `POST /plan`: request → LLM → candidates → optimizer → response (optional hotel start / round trip)
- [x] Response schema: days, ordered stops with arrive/leave times, street-following geometry (OSRM route), distance, time
- [x] Timeouts, clear errors (422 / 429 / 502 / 503 / 504), step timings in the response
- [x] Persist the route to `routes` / `route_stops` + full response; `GET /plans/{id}`
- [x] End-to-end integration tests (LLM mocked)
- [x] Transit for long legs: legs over 2.5 km become tram/metro/train (10 min + 15 km/h) and the optimizer minimises travel time. Live re-test: the Belém day is reached in 37 min instead of a 1 h 44 min walk, and no stops are dropped (2 were before)
- [x] Real transit routing: HERE Public Transit API (`HERE_API_KEY`) instead of the fixed-speed estimate. HERE has no transit matrix, so the optimizer plans with the estimate, fetches the real routes of the legs it rides, and plans again (at most 3 rounds, cached). Ridden legs are drawn along the line and list their rides (line, colour, stops, direction). Without a key, or when HERE fails, rides stay estimated. Live check: a 2-day trip from Rossio reaches Belém by metro Verde + Cascais line (42 min) and returns by bus 728 + metro, in 8.7 s end to end (~2 s more than before)
- [ ] (later) Ask HERE for less walking (`pedestrian[maxDistance]`) for transit-only travellers: today they get HERE's fastest itinerary, which can be mostly walking with a 1-stop ride

**DoD:** a single request returns a ready, optimized route.
**Result:** a live 2-day Lisbon request returns in ~3.6 s (LLM 2.4 s, optimization 0.6 s, geometry 0.6 s), with OSRM distances and zero crossings.

## Phase 6. Frontend
- [x] Next.js + TypeScript skeleton (Next.js 16, App Router, Tailwind; `/api/*` proxied to FastAPI)
- [x] eslint + prettier, added to pre-commit and CI (moved from Phase 0); vitest for the API client and formatters
- [x] Request form (text field + examples) and an optional start point picked on the map
- [x] Leaflet map: numbered markers, walking routes (solid) and transit legs (dotted), other days muted
- [x] POI cards, per-day tabs, total distance/time, travel leg between stops
- [x] Loading and error states (backend messages shown as is)
- [x] Mobile layout (map on top, plan below)
- [x] Share links: `?plan=<id>` reopens a saved plan

**DoD:** the user types a request and sees the route on the map.
**Result:** checked in a real browser (Playwright, desktop 1440 px and phone 390 px): plan, day switch, share link and error state work, with no console errors. Testing the error state found a real bug: "a weekend in Tokyo" was silently planned as Lisbon (fixed in `fix(llm): refuse unsupported cities`).

## Phase 6b. Refinements
- [x] Must-visit places: name search (`GET /places?q=`) and an autocomplete in the form; they always get a slot on some day if they fit the daily budget (trimmed only after every optional stop, moved to another day if their own day overflows)
- [x] Travel modes: walking and/or public transit (walking only: no tram/metro; transit only: ride every leg over 1 km)
- [x] Proximity-first selection: supplementary candidates ranked by PostGIS distance to the hotel and the must-visit places; the LLM sees the distances
- [x] Rich stop cards: Wikimedia photo with credit, short description (English Wikipedia / Wikidata), a personal note from the LLM, opening hours, website
- [x] Replace stops: tick stops of a day and replace them (`POST /plans/{id}/replace` → a new plan version). The LLM picks nearby places that fit the day's free time, never repeating a planned or rejected place; as a last resort, other stops of the day are adjusted when it ends up sparse or one-note, and every adjustment is reported. Undo returns to the previous version

**DoD:** a trip with a hotel and two must-visit places keeps both, its other stops cluster around them, and replacing a stop gives a new, non-duplicate place that fits the day.
**Result:** checked live (Gemini + OSRM) and in a browser (Playwright, desktop and phone). A 2-day trip from a hotel at Rossio with Jerónimos and the castle as must-visits keeps both and fills the rest around them, in ~6 s; replacing two stops takes ~2.5 s and keeps day 2 within its 8 h. 604 of 2,143 Lisbon places have a photo and 414 a description. The live runs found three problems, each with a regression test: a same-name twin of a must-visit place was picked (fixed); the LLM chose two 90-minute museums for 130 free minutes (the prompt now states the free time and visit lengths, a misfit is reported, and the filler fills the gap, but the LLM can still choose that way); and the free-time filler gave up after one candidate (fixed).

## Phase 6c. Weather-aware routing
- [x] Weather service: OpenWeatherMap 5 day / 3 hour forecast (`OPENWEATHER_API_KEY`) with temperature, chance of precipitation, rain/snow, fog, visibility, sunrise and sunset; cached, and a failure means a plan without weather
- [x] Indoor or outdoor places, from the category and OSM tags: palaces, monasteries and covered markets are indoor; viewpoints, parks, statues, castle walls and open-air markets are outdoor
- [x] Optimizer (soft time windows): an outdoor visit in rain, snow, fog, poor visibility or the dark costs like extra travel time. Days are matched to trip dates, each day is reordered, and outdoor stops trade days with indoor stops while that pays off
- [x] Selection: the LLM sees the forecast and which candidates are outdoor; a guard swaps the least important outdoor picks for the best-ranked indoor candidates when dry daylight cannot hold them
- [x] API: `start_date` and `weather_aware` in `POST /plan`; every day and stop carries its forecast; replacing stops keeps the weather
- [x] Frontend: first-day date, an "Optimize route based on weather conditions" checkbox, a weather header per day and the forecast on every stop card
- [ ] (later) Let a day pause when rain is about to pass (days can start later since Phase 6d, but never wait for the weather)
- [ ] (later) Prefer indoor swaps of a similar visit length: wet days pick more 90-minute museums, so more stops get trimmed

**DoD:** with the checkbox off, plans are what they were. With it on, a rainy afternoon gets the museums and the dry morning the viewpoints, outdoor stops end by sunset, and a wet day swaps outdoor picks for indoor places that suit the request.
**Result:** checked live in a browser (Gemini + OSRM + HERE, Playwright, desktop and phone), with OpenWeatherMap replaced by a local server for a rainy day (dry until 10:30, rain until 16:30): no key was available. Without the checkbox, 3 of 5 stops were outdoors in the rain and the plan said so; with it, the LLM chose museums for the rain, the castle got the dry 09:30 slot, and no outdoor stop met rain (5.7 → 3.4 km). It also showed the trimming problem above: 2 stops dropped instead of 1. On random 1–7 day trips, outdoor visits meet 80–100% less bad weather for 5–20% more travel, and a week of 56 stops takes ~50 ms longer to plan.

## Phase 6d. Custom day hours and evenings
- [x] Evening places: bars, pubs, clubs and fado houses (`nightlife`), fado and well-known restaurants (`restaurant`), and named squares (landmarks) from OSM; closed venues skipped
- [x] When a place can be visited, from its category and OSM tags: by day (indoor sights close at 20:00), in daylight (outdoor sights), at night (evening places open at 20:00), or any time (lit squares, venues open late per `opening_hours`)
- [x] Sunrise and sunset computed for every trip day, so darkness is known without a forecast
- [x] Optimizer (VRPTW): every day has its own hours (start, end past midnight allowed, daylight); a place visited too early waits for it to open, a visit past its closing time or sunset is not allowed (reordered, else dropped and reported). The pace is a share of the day's hours (relaxed ½, moderate ⅔, intense ⅚), so the default 09:30–21:30 day plans as before
- [x] Selection: places per day scale with the hours (a day from 16:00 gets 2–3 instead of 6); the LLM is told how many go before and after 20:00 and how many can be outdoors before dark, and a guard swaps picks that cannot take those slots
- [x] Weather only when the checkbox is on: no forecast is fetched otherwise; when on, rain, snow, fog and visibility count only within the day's hours (forecast slots of those hours, overnight included)
- [x] API: `day_start`, `day_end` (earlier than the start: the next morning) and `first_day_start` in `POST /plan`; a trip that starts today starts no earlier than now; days return their hours and daylight, stops their free time before them
- [x] Frontend: start and end time pickers (09:30–21:30 by default; today's start defaults to the current time in Lisbon, later days keep their own start), overnight hint, free time and evening places in the plan
- [x] Hours for each day: a Days field (`day_count`, "As described" by default) sets the number of days in place of the text's, and from 2 days on "Different hours each day" gives every day its own start and end (`day_hours`, labelled with its date and length); places per day follow each day's hours, a day may not run into the next, and saved plans reopen with them

**DoD:** a 09:30–21:30 day plans as before. A plan for today at 16:00 has 2–3 places from 16:00. 16:00–03:00 fills the afternoon with sights and outdoor places before sunset, and the night with bars, fado houses, restaurants and lit squares, never a museum or a viewpoint after dark. With the checkbox off no forecast is used; with it on, only the weather within the chosen hours counts.
**Result:** checked live (Gemini + OSRM + HERE + OpenWeatherMap) and in a browser (Playwright). 2,685 Lisbon places now, 406 of them bars, pubs and clubs, 48 fado and notable restaurants and ~90 squares. A default day plans as before; 16:00 to 21:30 gets 2–3 places (a viewpoint before the 17:41 sunset, then a museum); 16:00 to 03:00 gets an outdoor sight before dark and the Fado museum, free time, a fado dinner at 20:00 and two Bairro Alto bars; at 23:15 on the day itself the plan starts then and says so; with the checkbox on, the forecast covers 15:00 to 03:00 only. The live runs found three problems, each fixed with a regression test: a "fado" keyword filled the candidate pool with fado houses (five dinners, an empty afternoon), a day from 18:00 dropped an open museum before the viewpoint already in the dark, and the today hint misread a late start. The optimizer plans a week of 16:00–03:00 days with 49 mixed places in 0.3 s.
- [x] Per-venue opening hours from OSM `opening_hours` (days, opening and closing times): every trip day has its date, and a place's own hours on it replace the hours of its kind (a museum that closes at 18:00 is visited before then, a visit waits out a lunch break, the castle stays open until 21:00); outdoor sights still need daylight and evening places the evening, and unreadable or `unknown` hours keep the kind's. A stop closed on its day moves to another day that is open for it, in place of less important stops if need be; places closed on every trip day are no candidates, and replacements must be open on the day's date. When a visit runs late, only stops whose leaving makes the day less late are dropped
- [ ] (later) Breaks in the middle of a day (lunch, a rest): days only wait for places to open

## Phase 6.5. Profiles, live route editing and places to eat
A traveller saves a trip, ticks off places during the day and changes the rest of it on the go: removes a stop, adds a place, or finds somewhere to eat nearby and makes it the next stop. Generated plans suggest sights only; food and drink come from the search.

**Design notes**
- One edit for everything: removing stops, adding a place, "next stop" and "re-plan from my location now" are options of a single day edit; "Add to route" from the food search is just one call to it. The edit runs only the optimizer (no LLM), so it is fast and predictable
- Drafts are the approval step: an edit returns a draft version that the trip does not use yet. If it drops planned stops, the app lists them and says why; saving the draft approves it, Cancel leaves the trip unchanged. The same save makes the cycle repeatable
- Stops drop only when the day really runs long: a live re-plan must end by the day's end time (plus a short grace), not within the pace share, which would drop stops even when the day still ends on time
- The "original destination" is the hotel on round trips; plans without a hotel have no destination, so they stay open-ended
- The current location comes from the browser ("Use my location"), with a pin on the map as the fallback, defaulting to the last visited stop
- The stay at a venue is adjustable, with a default by type: a coffee and a dinner differ a lot
- Live editing needs a saved trip: visited places live on it, so there is one source of truth. Plans that are not saved keep the AI replace only
- Food data is OSM only for now: no ratings or prices exist there, so those filters wait for an optional provider (see the last items)

**Accounts and saved trips** (moved from Phase 9)
- [x] Accounts: `users` (email, argon2 password hash, display name) and `sessions` (hashed random token, expiry); `POST /auth/signup`, `/auth/login`, `/auth/logout`, `GET` / `DELETE /auth/me`; an HttpOnly, SameSite=Lax, `Path=/` cookie through the same-origin `/api` proxy; a limit on failed log-ins. Password reset waits for an email sender
- [x] Saved trips: `trips` (owner, title, current plan version) and `trip_visits` (place, visited at); `POST /trips` saves a plan, `GET /trips` lists mine, `GET /trips/{id}` returns the trip with its current plan and visited places, `PATCH /trips/{id}` renames it or switches it to another version of the same trip (save a draft, undo), `DELETE /trips/{id}`. Other users' trips answer 404; `?plan=<id>` share links stay public and read-only
- [x] Visited places: `PUT` / `DELETE /trips/{id}/visits/{place_id}`; later edits never move or drop a visited stop
- [x] Frontend: a header with My trips and log in / out, sign-up and log-in pages, a My trips page, "Save to my trips" on a plan (log in first, then it saves), `?trip=<id>` opens a saved trip, a "Visited" tick on its stop cards

**Editing a saved day**
- [x] Optimizer: a day can start from any point at any time and end at a different point (the hotel), using the TSP's existing `end` support; a live re-plan is bounded by the day's end time (+30 min grace) instead of the pace share, so planned stops drop only when the day would really run long. Least important stops go first (only those whose leaving shortens the day: an afternoon sight is no help when the evening runs long); visited, must-visit and newly added places are protected
- [x] `POST /trips/{id}/edit` (no LLM): `{day, remove, add, next, after, start, stay_min}`. Visited stops stay first, as they were; with `start` (the traveller's pinned location) on today's day, the rest of the day is planned from now; `next` is visited first (pin → venue is a fixed first leg), or right after `after`, a stop of the day (the day stays as planned up to it), then the remaining stops are reordered from it; the day keeps its end (the hotel on round trips, else open). The answer is a draft: a new plan version (`parent_id`, `edit` lists removed, added and dropped places) that the trip does not use yet. AI replace on a saved trip also returns a draft
- [x] Approval: when a draft drops planned stops, the app lists them and says why ("the day would end at 23:10 instead of 21:30"); only saving it (`PATCH /trips/{id}`) applies it, Cancel keeps the trip as it was. A draft made from an outdated version is refused (409)
- [x] Frontend: Edit mode on a saved day (remove a stop, add a place with the place search taken out of the must-visit picker), a draft banner (Save / Discard), a confirmation dialog for dropped stops, undo to the previous version. The traveller's location and the next stop come with the food search below
- [x] AI replace on a saved trip keeps visited stops first, as day edits do: `POST /trips/{id}/replace` knows the trip's visited places, refuses to replace them (422), keeps them first in their planned order and plans the rest of the day after them (until the day's end plus the grace, every dropped stop saying why); the frontend uses it on saved trips

**Sightseeing only by default** (replaces Phase 6d's evening venues)
- [x] Generated plans and AI replacements never suggest restaurants, cafés, bars, pubs, clubs or fado houses, even when the request names them; only must-visit places of these kinds are planned (dinner from 20:00, bars at night, as before). A request that asks for food or nightlife gets a note pointing to must-visit places (the search joins it once it exists, see below)
- [x] Evenings: after 20:00 only lit squares and late-open sights are offered (at most 2 per evening, from a pool of their own that never fills the afternoon); the rest is free time (`free_from`, "Free time from 21:40 until 03:00" after the last stop). Its "Find places to eat & drink" link comes with the search, see below
- [x] Update the evening tests, the hours hint and the README (a 16:00–03:00 day now has afternoon sights and a free evening)

**Places to eat and drink**
- [x] Import every named food and drink venue from OSM: all restaurants (not only well-known ones), cafés, fast food, ice cream, pastry shops, bars, pubs, clubs; a new `cafe` category; cuisine, `diet:*`, `opening_hours` and `outdoor_seating` stay in `tags`
- [x] Opening hours: parse OSM `opening_hours` (a maintained parser such as `opening-hours-py`) to tell "open now" and "open when you arrive"; hours it cannot read count as unknown
- [x] `GET /venues`: near a point (`ST_DWithin`, radius 250 m – 2 km) with filters for kind (food / drinks & nightlife), cuisine, vegetarian, vegan, open now and outdoor seating; sorted by distance, then by how complete a venue's data is; each result has its cuisine, diet tags, opening hours, open-now state, distance and walking minutes, plus the cuisines found in range for the filter
- [x] Frontend: "Find places to eat" on a saved trip turns the sidebar into the search, with the route still on the map; "Use my location" (browser geolocation) or a pin on the map, defaulting to the last visited stop; results as cards and markers; "← Back to route" always visible (browser Back and Esc too; `?trip=<id>&eat=1`). A free evening gets a "Find places to eat & drink" link that opens the search near the evening's last stop, and the note for food and nightlife requests points to the search too
- [x] Add to route: pick a venue, choose how long to stay (by default: café 30 min, bar 60 min, restaurant 75 min), and the day is re-planned through the day edit with the pin as the start and the venue as the next stop; the draft opens with the approval step; once saved, the search and the edit can be repeated. A venue chosen as the next stop is visited at once, not held to 20:00, and the draft warns when its own opening hours say it is closed then
- [x] The venue is always the next stop after where the search is: on a day under way, from the traveller now; else right after the stop searched around (or the stop nearest a pin), never pushed to the evening at the end of the day. "Visit" offers the other places in the day, and on a day ahead the search says whether venues are open when the traveller would set off for them, not now
- [ ] (later) Ratings and price from an optional provider (e.g. Foursquare: one call per search, cached, matched to OSM venues by name and distance; filters hidden without a key). Google Places is ruled out: its terms forbid showing Places content on a non-Google map
- [ ] (later) "Keep all and finish later" as an alternative to dropping stops

**DoD:** a user signs up, plans a day from a hotel (round trip) and saves it; nothing in it is a restaurant or a bar. Mid-day they tick two stops visited, search vegetarian food within 500 m of their pinned location and add a café: the draft keeps the visited stops, goes from the pin to the café first, reorders the rest and ends at the hotel by the day's end time; if it cannot, it lists the stops it would drop and nothing changes until they approve. Saving it and repeating with a bar works. Another user cannot see or edit the trip. A 16:00–03:00 day has afternoon sights and a free evening with the eat link.
**Result:** checked live in a browser (Gemini + OSRM, Playwright, desktop and phone). 7,192 Lisbon places now, 3,167 of them restaurants, 1,392 cafés and ~400 bars; 33 vegetarian places within 500 m of Rossio, and a 2 km search (2,128 venues) takes ~100 ms. A day planned at 13:47 from a hotel on Avenida da Liberdade (round trip) got four sights from 14:00, no venue, and the food note pointing to the search. With two stops ticked, Vertigo Café (vegetarian, 300 m from the last visited stop) went next from there, the rest was reordered and the day ended back at the hotel; its 75-minute stay left the castle in the dark, so the draft listed it and the dialog asked before saving. A bar then went next at once, with a warning that its own hours open it at 18:00. Another user got a 404 for the trip and for an edit of it; a 16:00–03:00 day has afternoon sights and a free evening from 21:51 whose link opens the search around its last stop. The live runs found three problems, each fixed: the parser refused the API's `datetime.UTC` clock, a bar chosen as the next stop waited until 20:00, and a pin dropped among the crowded venue markers picked a venue instead.

## Phase 7. Quality and reliability
- [x] E2E tests (Playwright): the real frontend (production build) and API on a database of their own (seeded Lisbon sights, scripted LLM), desktop and phone: plan by day and reopen the share link, a plan without the AI, a request naming another city, replace a stop and undo, sign up, save, tick visited and reopen from My trips, log in before saving; a CI job runs them against a PostGIS service
- [x] Structured logs, request id: one handler for every log line (JSON with `LOG_FORMAT=json`); each request gets an id (the caller's `X-Request-ID` when plain, else a new one) that every line it logs carries and its response returns, and one line once answered (status, duration, client). LLM answers and new plans are logged with their numbers (tokens, timings)
- [x] Rate limiting and protection against LLM abuse: the endpoints that call the LLM allow each client (address) 5 requests a minute and 100 a day, then 429 with `Retry-After`; on top of the daily token budget, the response cache, the request size caps and output limited to a schema of candidate ids
- [x] Handling LLM outages (fallback / clear message): one LLM call ends within 40 s, retries included, and after 3 failed calls in a row a circuit breaker skips the LLM for 60 s (`GET /health` says so). When it fails (down, budget used up, refusing), plans are still made: rules read the request (city, days, interests and what to avoid, pace, names) and the best-ranked candidates are chosen; the plan says so (`ai_fallback` and its rationale, a notice in the frontend), and replacements take the best-ranked places that fit
- [x] Check that no secrets are in the repository: gitleaks found nothing in the 167 commits of every branch, the only env files ever committed are the `.env.example` files, and no provider key pattern is in the history; CI's `secrets` job now scans the whole history on every push (pre-commit only scans what is committed)
- [x] (Phase 8) Client addresses behind the deployed proxy: the Next.js proxy passes on the `X-Forwarded-For` the browser sent, unchanged, or none (every user one client). In the production stack a Caddy edge sets it to the address the request came from and sends `/api/*` straight to uvicorn, which trusts only the edge's fixed address (`FORWARDED_ALLOW_IPS`). Checked: a claimed `X-Forwarded-For: 6.6.6.6` is logged with the real address, and six plan requests each claiming another address get a 429 on the sixth

**Result:** 737 backend tests and 12 end-to-end runs (6 scenarios, desktop and phone, ~25 s after a ~1 min build) pass. Run under uvicorn, every line is JSON with its request id, and a caller's `X-Request-ID` comes back on the response. With the LLM failing, a plan still comes back in milliseconds and says it was made without the AI; the end-to-end run checks the notice in the browser. Writing the fallback's request reader found that matching word beginnings would read "Barcelona" and "baroque" as bars (now whole words only). The first end-to-end runs found two things about the app, not bugs: Next.js 16 keeps the page left behind in the document, hidden (its fields have to be found by role), and a replaced stop can bring a filler along when the day gets shorter.

## Phase 8. Deployment
- [x] Dockerfiles for backend and frontend: python:3.12-slim (non-root, run from source so the importers keep their cache; the same image runs migrations and imports) and a standalone Next.js server on node:24-alpine (43 MB of its own; `BACKEND_URL` and the tile settings are build arguments). `docker-compose.prod.yml` runs the whole app on one host: Caddy edge (automatic HTTPS), frontend, API, a `migrate` step, PostGIS and OSRM
- [x] Self-hosted OSRM (Docker, `osrm/`): the public server took ~10 s for most 25-point tables, and its 10 s timeout silently falls back to straight lines. Not a Portugal extract: Berlin and Barcelona joined since, so each city's bbox plus 3–5 km is cut out of its Geofabrik region (Portugal, Berlin and Brandenburg, Catalonia) and built into one foot graph (MLD; a test keeps the areas in step with the cities). The same tables take 50–300 ms, in ~100 MB of RAM (memory-mapped); the build downloads ~900 MB and processes them in about a minute. A point OSRM moves over 1 km to reach a street (outside the graph's areas) falls back to haversine instead of being measured from there. A live 2-day plan through the stack took 4.4 s with OSRM distances
- [x] Map tiles from a provider with an API key: Mapbox Streets with `NEXT_PUBLIC_MAPBOX_TOKEN` (512 px tiles one zoom level down, a quarter of the billable requests of 256 px ones), greyed like before, with the logo and the "Improve this map" link Mapbox requires; OpenStreetMap's tiles without a token. Checked in a browser, desktop and phone; the first look found the attribution covering the logo on a phone (fixed)
- [x] CI/CD (GitHub Actions): every push to `main` and every pull request runs the pre-commit checks (ruff, mypy, file hygiene), gitleaks over the whole history, the backend tests (with their own PostGIS container), the frontend's lint, format, type check, unit tests and build, and the end-to-end tests against a PostGIS service. Render deploys the API once a commit's checks have passed (`autoDeployTrigger: checksPass`), and only for changes in `backend/`
- [x] Hosting: Render (API), Neon (PostGIS), Vercel (frontend), live at https://smart-travel-planner-liard.vercel.app. The API is a Blueprint (`render.yaml`: free plan in Frankfurt next to Neon, deploys once CI passes), migrates as the image starts (no pre-deploy step on the free plan) and answers only the website: Vercel's proxy adds an origin secret (otherwise a caller skipping Vercel could claim any `X-Forwarded-For`). Connections are checked before use (Neon closes them when it suspends). Checked live: the site's `/api/health` answers `ok` for the database and the LLM, and plans made on the site are saved in Neon and reopen from their links
- [x] Secrets via hosting environment variables: the API's `DATABASE_URL`, LLM, HERE and OpenWeatherMap keys and `ORIGIN_SECRET` are set in Render (`sync: false` in the Blueprint: asked for once, never in the repository), the frontend's `BACKEND_URL`, `ORIGIN_SECRET` and Mapbox token in Vercel; the repository holds only `.env.example`
- [x] Demo link and screenshots in the README: https://smart-travel-planner-liard.vercel.app, a sample 2-day Lisbon plan, and three screenshots of the live site (`docs/screenshots/`: the planner, a day with walks and rides, a day on a phone)

## Phase 9. Post-MVP
- [x] Export (GPX, Google Maps link): `GET /plans/{id}/gpx` (every day or `?day=`) gives a GPX 1.1 file (valid against the official schema): stops as waypoints with their arrival times and notes, days as tracks along the drawn geometry. The Export panel opens the selected day in Google Maps: walks in a row as one route (in balanced parts past 9 waypoints), each ride as its own transit route, the way back by the day's `return_mode`; on a day under way, from where the traveller is through the stops left
- [x] Multiple cities: Berlin and Barcelona join Lisbon (bounding box, time zone, country for public holidays); 19,655 and 11,302 places imported and enriched. Closed places are recognised in German, Spanish and Catalan too, and an Overpass answer cut short is never cached. `GET /cities` lists them; `POST /plan` takes `city` (a text that names another city gets a 422)
- [x] Frontend: choose the city (`GET /cities`); the map, clock and place search follow it. Cities with their local time at the top of the request form; dates, the place search, examples and the map follow it, and `POST /plan` gets `city`. A text that names another city is caught before planning with a one-click switch (the backend's 422 stays as the last word); changing the city clears the old city's start point and must-visit places, with Undo. Shared plans and trips bring their own city; `?city=` links and the last choice on the device pick the default
- [x] Rank candidates by fame: `app.ingest.enrich` counts the Wikipedia languages that cover each place (Wikidata sitelinks, `places.wikipedia_languages`), and the score grows with its log (1 language 0.6, 30 give 3, 100 give 4) in place of having a Wikidata or Wikipedia link, which tied hundreds of sights at the top (991 in Berlin). One place per Wikidata item (24 pieces of Lisbon's aqueduct shared one). Weights alone could not do it: the request's interests are a guess at categories, and with "landmark" for a Gaudí day hundreds of squares outranked the Sagrada Família (a church), with "landmark, monument" for Berlin's classics the Reichstag (an attraction). So the city's most famous places, a third of the pool's size, always join it, and they lead the list the LLM sees: from 31st place a small model passed over the Sagrada Família in 6 of 6 runs, from the top it picked it every time
- [x] Buildings mapped as artworks (`artwork_type=architecture`: Casa Batlló, Casa Milà) were outdoor monuments with short visits: those that open to visitors (a building with opening hours) are indoor landmarks now (45 min, by day; Casa Milà, open until 23:00, any time), façades without hours stay monuments (Casa Calvet). The importer does it, and migration 0011 recategorizes the rows imported before (2 of the 35 such places: the importer and the migration agree on all 35)
- [x] Drag-and-drop stops with route recalculation (reuse the Phase 6.5 day edit): `POST /trips/{id}/edit` takes `order`, the day's stops not visited in the traveller's order, kept as it is (nothing reordered or dropped; the draft warns when it runs late or reaches a place closed or dark, and says how much longer it is than the optimizer's order). A saved day's stop numbers are drag handles (mouse, touch, pen, and the keyboard: Space, arrows, Escape); a drop opens a draft with the new times and route, whose stops can move again before it is saved. Checked end to end in a browser, desktop and phone
- [x] More cities, on the free plans: 44 more of the most visited cities, 47 in all (Europe 29, the Americas 7, Asia 8, Africa and Oceania 3), each with the bbox of its administrative boundary from Nominatim (by hand where that is far too big: Tokyo's 23 wards, central Istanbul), time zone, country and local names. Nice is left out ("a nice day" would name it), and Washington is "Washington, D.C." ("Washington Square" in a New York request is no city). The city list is grouped by part of the world. What the new cities needed: closed places recognised in their languages and scripts; places whose OSM name is in another script named in English (OSM's English name or romanization, else the English label of their Wikidata item); Commons asked with POST (Thai file names overflowed a URL); a third Overpass mirror (the other two failed for hours); and only the OSM tags the app reads stored, so all of it fits Neon's free 0.5 GB. Imported and enriched locally: 520,317 places (Seoul 55k, Tokyo 45k, London 39k, down to Marrakesh's 831), 35,474 with a photo and 34,883 with a description; 2,054 named by their Wikidata label (Tokyo 1,405, Kyoto 285), and 1,488 Wikidata links left out as not the place. Hong Kong's and Singapore's places come from within their borders only (their bboxes took in 1,800 places in Shenzhen and 190 in Johor Bahru). Estimated ~280 MB of Neon's 0.5 GB
- [x] Fame only from Wikidata items that are the place: OSM often links a statue, grave or memorial to the person it is about, which made a Roosevelt statue Buenos Aires' most famous place and a standard-metre plaque outrank the Eiffel Tower. An item counts when Wikidata locates it in the city; the rest, and the Wikipedia article OSM links with it, are left out (fame, photo, description and name)
- [ ] (later) Seoul's and Taipei's small venues keep their names in Hangul and Chinese characters: OSM has no English name for most of them
- [ ] (later) The self-hosted OSRM image with all 47 cities downloads ~20 GB; measure its build time and memory, or let a deployment choose its cities
- [ ] Mapbox GL instead of Leaflet (if needed)

---

## Risks
| Risk | Mitigation |
|---|---|
| POI quality and coverage | One city, OSM data + manual cleanup |
| Haversine produces fake "short" routes (rivers, barriers) | Switch to OSRM/Valhalla (Phase 4) |
| LLM latency and cost | Structured output, small model, caching |
| LLM hallucinations | Selection only by `id` from the candidate list |
| Weak differentiation from competitors | Position as an engineering project with a measurable metric |
