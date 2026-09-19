#!/usr/bin/env bash
# Canonical backend: loopback 8504 behind Caddy. Override for laptop development.
set -euo pipefail
PULSE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PULSE_ROOT"
PULSE_PYTHON="${PULSE_ROOT}/.venv/bin/python"
if [[ ! -x "$PULSE_PYTHON" ]]; then
  PULSE_PYTHON="${PULSE_ROOT}/api/.venv-pulse/bin/python"
fi
if [[ ! -x "$PULSE_PYTHON" ]]; then PULSE_PYTHON="$(command -v python3)"; fi
exec env PYTHONPATH=src "$PULSE_PYTHON" -m uvicorn api.main:app --host "${PULSE_HOST:-127.0.0.1}" --port "${PULSE_PORT:-8504}"
