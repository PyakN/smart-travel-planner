# The API: FastAPI under uvicorn, as a non-root user, on port 8000. Settings come from the
# environment (app/config.py); see the root README's Deployment section.
#
#   docker build -t travel-planner-api backend
#   docker run --env-file .env -p 8000:8000 travel-planner-api
#   docker run --env-file .env travel-planner-api alembic upgrade head       # migrations
#   docker run --env-file .env travel-planner-api python -m app.ingest lisbon
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# The dependencies alone first, so a code change reuses this layer.
COPY pyproject.toml ./
RUN python -c "import tomllib; deps = tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']; print(*deps, sep='\n')" > requirements.txt \
    && pip install -r requirements.txt \
    && rm requirements.txt

# Run from source in /app rather than installed: the importers keep their cache in /app/data.
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
RUN python -m compileall -q app migrations \
    && useradd --system --uid 10001 --no-create-home app \
    && mkdir data \
    && chown app data
USER app

EXPOSE 8000
# Client addresses: uvicorn reads X-Forwarded-For only from FORWARDED_ALLOW_IPS (127.0.0.1
# unless set), which must name the proxy in front. Keep-alive outlasts the proxy's idle
# connections (60 s in deploy/Caddyfile), so it never reuses one that uvicorn just closed.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "75"]
