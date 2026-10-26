# Smart AI Travel Planner

A travel planner with a two-layer architecture:

1. **LLM** (Gemini / OpenAI) parses the user's request and selects interesting places from our database.
2. **Geo-optimizer** (TSP / PostGIS) reorders those places into the shortest walking route, with no zigzags.

Stack: FastAPI · PostgreSQL + PostGIS · Next.js + Leaflet. Roadmap: [PROJECT_PLAN.md](PROJECT_PLAN.md). Dev rules: [CLAUDE.md](CLAUDE.md).

## Layout

```
backend/    FastAPI app (Python 3.12+)
frontend/   Next.js app (Phase 6)
docs/       Notes and benchmarks
```

## Getting started

Prerequisites: Docker, Python 3.12+.

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

# 5. Git hooks (run from the repo root)
cd ..
pre-commit install
```

The importer caches the raw Overpass response in `backend/data/raw/`. Re-runs use the cache and upsert by OSM id; pass `--refresh` to fetch fresh data.

## API

```bash
cd backend
uvicorn app.main:app --reload      # http://localhost:8000/docs for interactive docs
```

| Endpoint | Description |
|---|---|
| `GET /health` | Service and database status |
| `GET /places` | Search: `city`, `category` (repeatable), `bbox=west,south,east,north`, or `lat`+`lon`+`radius_m` (sorted by distance); `limit` / `offset` |
| `GET /places/{id}` | One place |
| `GET /categories` | Categories with place counts (optional `city`) |
| `POST /plan` | **Plan a trip from text**: `{"text": "...", "start": {"lat", "lon", "round_trip"}?}` → days with ordered, timed stops and map geometry. Saved; returns `id` |
| `GET /plans/{id}` | A saved plan |

Example: museums and viewpoints within 400 m of Praça do Comércio:

```
GET /places?lat=38.7075&lon=-9.1364&radius_m=400&category=museum&category=viewpoint
```

Plan a trip (needs an LLM key in `.env`):

```bash
curl -X POST localhost:8000/plan -H "Content-Type: application/json" \
  -d '{"text": "2 days in Lisbon: viewpoints, the castle and Belém", "start": {"lat": 38.7139, "lon": -9.1394}}'
```

Error statuses:
- **422:** the request can't be planned, for example an unsupported city.
- **429:** the daily LLM token budget is used up.
- **502:** the LLM rejected the request.
- **503:** the LLM is unavailable or not configured.
- **504:** planning timed out.

## LLM layer

The LLM never invents places. A request goes through four steps:

1. **Parse:** the request text becomes a `TripRequest` (city, days, interests, avoid, pace, keywords).
2. **Candidates:** SQL ranks the city's places by notability, interests and keywords.
3. **Select:** the LLM picks place ids from that candidate list.
4. **Guard:** a deterministic check drops any id that isn't a candidate.

Configure it in `.env`: `LLM_PROVIDER`, the matching API key, and optionally `LLM_MODEL` and `LLM_FALLBACK_MODEL`.

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
- **Transit:** legs over 2.5 km (e.g. the centre to Belém) are taken by tram, metro or train: 10 min overhead + 15 km/h. The optimizer minimises total travel time; each stop says how to get there (`travel_mode`), and the map geometry is split into walking and transit segments.

Results against LLM-only ordering are in [docs/benchmark.md](docs/benchmark.md): **55% less walking than the selection order, and on par with an itinerary the LLM arranged itself, with zero route crossings.**

```bash
cd backend
python evals/route_benchmark.py    # live benchmark (LLM + OSRM)
```

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
