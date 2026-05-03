#!/usr/bin/env sh
set -eu

echo "[entrypoint] Checking configuration..."
python -m app.main --check-config

echo "[entrypoint] Running health-check..."
python -m app.main --health-check

echo "[entrypoint] Applying database migrations..."
alembic upgrade head

echo "[entrypoint] Starting bot..."
exec python -m app.main --run-bot
