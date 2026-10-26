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
- [ ] FastAPI skeleton, package layout (api / services / repositories / schemas)
- [ ] Config via `pydantic-settings`
- [ ] `GET /health`
- [ ] Async DB access (SQLAlchemy 2 + asyncpg)
- [ ] `GET /places` (filters: category, bbox, radius)
- [ ] Tests: pytest + DB in a container
- [ ] CI job: lint + tests

**DoD:** tests are green; endpoints are documented at `/docs`.

## Phase 3. LLM layer
- [ ] Provider abstraction (`LLMClient`) with Gemini and OpenAI implementations
- [ ] Parse the request into structured JSON: `{city, days, interests, pace, constraints}` (structured output + Pydantic validation)
- [ ] Candidate generation from the DB: tag/category filter + ranking
- [ ] LLM picks POIs from the candidate list (by `id`, not by name)
- [ ] Guard: the LLM cannot return an id that is not among the candidates
- [ ] Retries, timeouts, response cache, spending limits
- [ ] Tests with a mocked LLM + a small set of eval prompts

**DoD:** a request text yields a list of valid `place_id`s in reasonable time.

## Phase 4. Geo-optimization
- [ ] Distance matrix: haversine first
- [ ] TSP solver: nearest neighbour + 2-opt
- [ ] Split into days: `ST_ClusterKMeans` / k-means
- [ ] Starting point (hotel / city centre / user-defined)
- [ ] Real walking distances: OSRM / Valhalla (foot profile)
- [ ] OR-Tools for comparison/improvement
- [ ] Constraints: opening hours, visit duration, daily time budget
- [ ] Benchmark: LLM order vs optimizer (km, self-intersections)

**DoD:** on test sets the route is never longer than the baseline order; metrics recorded in `docs/benchmark.md`.

## Phase 5. Planning API
- [ ] `POST /plan`: request → LLM → candidates → optimizer → response
- [ ] Response schema: days, ordered stops, geometry, distance, time
- [ ] Timeouts, clear errors, step tracing (for debugging)
- [ ] Persist the route to `routes` / `route_stops`
- [ ] End-to-end integration tests (LLM mocked)

**DoD:** a single request returns a ready, optimized route.

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
