#!/usr/bin/env bash
# Start the mobile trading-insights API (paper trading only) on port 8504.
set -euo pipefail
cd "$(dirname "$0")/.."   # options-seller/ (so `api` and `src` resolve)
exec ~/workspace/venv-money/bin/python -m uvicorn api.main:app \
  --host 127.0.0.1 --port 8504
