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
- [ ] (later) Real transit routing (GTFS / OpenTripPlanner) instead of the fixed-speed estimate

**DoD:** a single request returns a ready, optimized route.
**Result:** a live 2-day Lisbon request returns in ~3.6 s (LLM 2.4 s, optimization 0.6 s, geometry 0.6 s), with OSRM distances and zero crossings.

## Phase 6. Frontend
- [ ] Next.js + TypeScript skeleton
- [ ] eslint + prettier, added to pre-commit (moved from Phase 0)
- [ ] Request form (text field + examples)
- [ ] Leaflet map: numbered markers, route polyline
- [ ] POI cards, per-day tabs, total distance/time
- [ ] Loading and error states
- [ ] Mobile layout

**DoD:** the user types a request and sees the route on the map.

## Phase 7. Quality and reliability
- [ ] E2E tests (Playwright)
- [ ] Structured logs, request id
- [ ] Rate limiting and protection against LLM abuse
- [ ] Handling LLM outages (fallback / clear message)
- [ ] Check that no secrets are in the repository

## Phase 8. Deployment
- [ ] Dockerfiles for backend and frontend
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
