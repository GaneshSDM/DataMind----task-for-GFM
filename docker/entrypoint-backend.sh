#!/usr/bin/env bash
# Backend entrypoint: run DB migrations, optionally seed, then start the API.
set -e
cd /app/backend

echo "[backend] Running alembic migrations..."
alembic upgrade head || echo "[backend] alembic upgrade failed/skipped — check DATABASE_URL"

if [ "${SEED_DB:-false}" = "true" ]; then
  echo "[backend] Seeding database (admin user + agent configs)..."
  python seed.py || echo "[backend] seed.py failed/skipped (may already be seeded)"
fi

echo "[backend] Starting uvicorn on 0.0.0.0:8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
