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
- [ ] Constraints: opening hours (OSM `opening_hours` not parsed yet)
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

**DoD:** a 09:30–21:30 day plans as before. A plan for today at 16:00 has 2–3 places from 16:00. 16:00–03:00 fills the afternoon with sights and outdoor places before sunset, and the night with bars, fado houses, restaurants and lit squares, never a museum or a viewpoint after dark. With the checkbox off no forecast is used; with it on, only the weather within the chosen hours counts.
**Result:** checked live (Gemini + OSRM + HERE + OpenWeatherMap) and in a browser (Playwright). 2,685 Lisbon places now, 406 of them bars, pubs and clubs, 48 fado and notable restaurants and ~90 squares. A default day plans as before; 16:00 to 21:30 gets 2–3 places (a viewpoint before the 17:41 sunset, then a museum); 16:00 to 03:00 gets an outdoor sight before dark and the Fado museum, free time, a fado dinner at 20:00 and two Bairro Alto bars; at 23:15 on the day itself the plan starts then and says so; with the checkbox on, the forecast covers 15:00 to 03:00 only. The live runs found three problems, each fixed with a regression test: a "fado" keyword filled the candidate pool with fado houses (five dinners, an empty afternoon), a day from 18:00 dropped an open museum before the viewpoint already in the dark, and the today hint misread a late start. The optimizer plans a week of 16:00–03:00 days with 49 mixed places in 0.3 s.
- [ ] (later) Per-venue opening hours from OSM `opening_hours` (days, opening and closing times): today indoor sights all close at 20:00, so a museum that closes at 18:00 can be planned until 18:30
- [ ] (later) Breaks in the middle of a day (lunch, a rest): days only wait for places to open

## Phase 7. Quality and reliability
- [ ] E2E tests (Playwright)
- [ ] Structured logs, request id
- [ ] Rate limiting and protection against LLM abuse
- [ ] Handling LLM outages (fallback / clear message)
- [ ] Check that no secrets are in the repository

## Phase 8. Deployment
- [ ] Dockerfiles for backend and frontend
- [ ] Self-hosted OSRM (Docker, Portugal extract): the public server takes 1–10 s per matrix, most of a plan's time, and its 10 s timeout silently falls back to straight lines
- [ ] Map tiles from a provider with an API key (the public OSM tile server is for light use only)
- [ ] CI/CD (GitHub Actions)
- [ ] Hosting: Fly.io / Render (API), Neon / Supabase (PostGIS), Vercel (frontend)
- [ ] Secrets via hosting environment variables
- [ ] Demo link and screenshots in the README

## Phase 9. Post-MVP
- [ ] Authentication and saved trips
- [ ] Export (GPX, Google Maps link)
- [ ] Multiple cities
- [ ] Drag-and-drop stops with route recalculation
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
