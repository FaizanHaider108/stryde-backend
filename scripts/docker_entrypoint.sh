#!/bin/sh
# Render starts the container with PORT set; migrations run automatically (no Shell needed).
set -e

PORT="${PORT:-8000}"
export APP_ROOT="/app"
cd "$APP_ROOT"

echo "==> Stryde API startup (port $PORT)"

if ! python3 scripts/prepare_db.py; then
  echo "==> Database preparation failed — container exiting."
  exit 1
fi

echo "==> Starting uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
