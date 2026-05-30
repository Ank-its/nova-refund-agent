#!/usr/bin/env bash
set -e

echo "[entrypoint] Running database migrations..."
alembic upgrade head

echo "[entrypoint] Seeding database (idempotent)..."
python -m app.seed

echo "[entrypoint] Starting API server on :8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
