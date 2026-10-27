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
