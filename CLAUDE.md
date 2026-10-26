# CLAUDE.md — development rules

## Project
Smart AI Travel Planner: an LLM picks places from the database, an algorithm (TSP / PostGIS) builds the shortest walking route.
Stack: Python (FastAPI), PostgreSQL + PostGIS, Next.js + Leaflet. Roadmap: `PROJECT_PLAN.md`.

## Language
Everything in English: code, comments, docs, commit messages, and communication.

## Layout (target)
- `backend/` — FastAPI, Alembic migrations, pytest tests
- `frontend/` — Next.js
- `docs/` — notes and benchmarks

## Commits: Conventional Commits
Format: `<type>(<scope>): <description>` — imperative mood, up to ~72 characters, no trailing period.

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
Scope (optional): `backend`, `frontend`, `db`, `llm`, `optimizer`, `infra`.

Examples:
- `feat(optimizer): add 2-opt improvement for TSP route`
- `fix(db): add missing GIST index on places.geom`
- `chore: initial repository setup`

Breaking change: `!` after the type/scope and an explanation in the commit body.

## Atomic commits
- One commit = one logical change.
- Don't mix a feature, a refactor and formatting in one commit.
- Tests go in the same commit as the code they cover.
- Every commit must leave the project working (build and tests pass).
- Stage files explicitly (`git add <files>`), never a blind `git add -A`. Check `git status` and `git diff --staged` before committing.

## Secrets and .env — strictly forbidden
- **Never** commit or push `.env` or any file with keys/tokens/passwords (`GEMINI_API_KEY`, `OPENAI_API_KEY`, DB passwords, etc.).
- The repository only holds `.env.example` with empty/dummy values.
- Never hardcode keys in code, tests, logs or docs.
- If a secret lands in a commit, treat it as compromised: rotate the key first, then clean the history.

## Never commit
`.env`, `venv/`, `.venv/`, `node_modules/`, `.claude/`, caches and build artifacts (see `.gitignore`).

## Code rules
- Python: type hints required, ruff for formatting and linting, mypy for type checking.
- TypeScript: strict mode, eslint + prettier.
- The LLM returns only structured JSON, which is validated (Pydantic). Places are selected by `id` from the candidate list; the LLM never decides coordinates or visiting order.
- Geo queries go through PostGIS (`geography`, `ST_DWithin`) with GIST indexes.
- New logic comes with tests; external APIs (LLM) are mocked in tests.

## Workflow
- For non-trivial changes, write a short plan first, then implement in small steps following `PROJECT_PLAN.md`.
- When a step is done, tick it in `PROJECT_PLAN.md`.
- Main branch is `main`; feature work goes in `feat/...`, `fix/...` branches.
