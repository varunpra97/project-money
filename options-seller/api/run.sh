#!/usr/bin/env bash
# Start the Pulse mobile API (paper trading only) on 127.0.0.1:8504.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi
exec env PYTHONPATH=src "$PY" -m uvicorn api.main:app --host 127.0.0.1 --port 8504
