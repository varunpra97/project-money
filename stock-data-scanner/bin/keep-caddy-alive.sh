#!/usr/bin/env bash
# Keep Caddy alone on :8080 for the public tunnel.
exec 9>/tmp/scanner-caddy-watchdog.lock
flock -n 9 || exit 0
CADDY=/tmp/caddy
CFG=/workspace/stock-data-scanner/Caddyfile
LOG=/tmp/caddy-scanner.log
while true; do
  # Evict aiohttp proxy if present (by exact script name)
  for pid in $(pgrep -f '/workspace/stock-data-scanner/.venv/bin/python proxy_server.py' || true); do
    kill "$pid" 2>/dev/null || true
  done
  for pid in $(pgrep -f 'python json_api' || true); do
    :
  done
  if ! curl -sf --max-time 2 http://127.0.0.1:8080/_stcore/health >/dev/null 2>&1; then
    # Only kill caddy processes for this config
    for pid in $(pgrep -f '/tmp/caddy run --config /workspace/stock-data-scanner/Caddyfile' || true); do
      kill "$pid" 2>/dev/null || true
    done
    sleep 1
    # free port if something else holds it
    if ss -tln | grep -q ':8080'; then
      fuser -k 8080/tcp >/dev/null 2>&1 || true
      sleep 1
    fi
    nohup "$CADDY" run --config "$CFG" --adapter caddyfile >>"$LOG" 2>&1 &
    sleep 2
  fi
  sleep 5
done
