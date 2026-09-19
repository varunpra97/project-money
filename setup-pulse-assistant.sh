#!/bin/bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
npm install --prefix "$PROJECT_DIR/.pulse-tools" @openai/codex@0.155.1 --no-audit --no-fund
CODEX_BIN="$PROJECT_DIR/.pulse-tools/node_modules/.bin/codex"
if ! "$CODEX_BIN" login status; then
  "$CODEX_BIN" login
fi
printf '%s\n' 'Assistant runtime ready. Start Pulse, open Assistant, and pair your iPhone using the code shown on localhost.'
