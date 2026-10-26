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

# 4. Git hooks (run from the repo root)
cd ..
pre-commit install
```

## Everyday commands

```bash
docker compose up -d --wait        # start the database
docker compose down                # stop it (data persists in the pgdata volume)

cd backend
ruff check . && ruff format .      # lint + format
mypy                               # type check
pytest                             # tests

pre-commit run --all-files         # run every hook manually
```

## Secrets

Never commit `.env`. Only `.env.example` lives in git. A pre-commit hook blocks `.env` files, and gitleaks scans for hardcoded secrets.
