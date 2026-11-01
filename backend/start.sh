#!/bin/sh
# Starts the API on $PORT (8000 unless the host sets it, as Render does). With
# MIGRATE_ON_START=true it brings the schema up to date first, for hosts without a step of
# their own for that (Render's free plan; docker-compose.prod.yml has a `migrate` service).
set -e
if [ "${MIGRATE_ON_START:-false}" = "true" ]; then
	alembic upgrade head
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --timeout-keep-alive 75
