#!/bin/bash
# Container entrypoint: seed demo data on first boot, then serve the API.
set -euo pipefail

DATA_DIR="${PULSE_DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"

if [ ! -f "$DATA_DIR/paper_portfolio.json" ]; then
  echo "[entrypoint] seeding demo paper portfolio"
  cp /app/options-seller/api/seed_portfolio.json "$DATA_DIR/paper_portfolio.json"
fi

PORT="${PORT:-8504}"
cd /app/options-seller
exec env PYTHONPATH=/app/options-seller/src \
  python -m uvicorn api.main:app --host 0.0.0.0 --port "$PORT"
