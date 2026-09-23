#!/bin/bash
# Container entrypoint: seed demo data on first boot, then serve the API.
set -euo pipefail

DATA_DIR="${PULSE_DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"

if [ ! -f "$DATA_DIR/paper_portfolio.json" ]; then
  echo "[entrypoint] seeding demo paper portfolio"
  cp /app/options-seller/api/seed_portfolio.json "$DATA_DIR/paper_portfolio.json"
fi

# Seed scan + volatility snapshots so the API serves data from the first
# request after a cold boot (Render free tier sleeps; /data is ephemeral).
# The background workers overwrite these with fresh data within minutes.
if [ ! -f "$DATA_DIR/scan-latest.json" ]; then
  if [ -f /app/seed/scan-latest.json ]; then
    echo "[entrypoint] seeding scan snapshot"
    cp /app/seed/scan-latest.json "$DATA_DIR/scan-latest.json"
  elif [ -f /app/stock-data-scanner/scan-latest.json ]; then
    echo "[entrypoint] seeding scan snapshot (repo fallback)"
    cp /app/stock-data-scanner/scan-latest.json "$DATA_DIR/scan-latest.json"
  fi
fi
if [ ! -f "$DATA_DIR/thetahedge-latest.json" ] && [ -f /app/seed/thetahedge-latest.json ]; then
  echo "[entrypoint] seeding thetahedge snapshot"
  cp /app/seed/thetahedge-latest.json "$DATA_DIR/thetahedge-latest.json"
fi

PORT="${PORT:-8504}"
cd /app/options-seller
exec env PYTHONPATH=/app/options-seller/src \
  python -m uvicorn api.main:app --host 0.0.0.0 --port "$PORT"
