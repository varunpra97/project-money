#!/bin/bash
# Start the Pulse backend on this Mac.
# Run:  bash ~/project-money/start-pulse-backend.sh
# The API will be available at http://<this-mac-ip>:8505/pulse
# (bound to 0.0.0.0 so a physical iPhone on the same Wi-Fi can reach it).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$PROJECT_DIR/options-seller/api"
DATA_DIR="$PROJECT_DIR/options-seller/data"
DATA_DIR="${PULSE_DATA_DIR:-$DATA_DIR}"
DATA_DIR="$(python3 -c 'import os,sys; p=os.path.expanduser(sys.argv[1]); print(p if os.path.isabs(p) else os.path.join(sys.argv[2],p))' "$DATA_DIR" "$PROJECT_DIR/options-seller")"
export PULSE_SCAN_COLLECTOR="${PULSE_SCAN_COLLECTOR:-1}"
VENV_DIR="$API_DIR/.venv-pulse"
PORT="${PULSE_PORT:-8505}"

mkdir -p "$DATA_DIR"
cd "$API_DIR"

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install -r "$API_DIR/requirements.txt"
npm --prefix "$PROJECT_DIR/mobile-app" ci
npm --prefix "$PROJECT_DIR/mobile-app" run build

# Seed demo paper-trading portfolio if missing
if [ "${PULSE_SEED_DEMO:-0}" = "1" ] && [ ! -f "$DATA_DIR/paper_portfolio.json" ]; then
  echo "Seeding demo paper portfolio..."
  cat > "$DATA_DIR/paper_portfolio.json" <<'SEED_EOF'
{
  "cash": 101170.0,
  "starting_cash": 100000.0,
  "premium_collected_lifetime": 1225.0,
  "realized_pnl_lifetime": 220.0,
  "positions": [
    {
      "id": "10077dba-c487-442e-8e69-4f37ce7fde08",
      "underlying": "AAPL",
      "strategy": "cash_secured_put",
      "legs": [{"symbol": "AAPL", "option_type": "put", "strike": 210.0, "dte": 32, "side": "sell", "quantity": 1, "delta": -0.22}],
      "credit": 320.0, "capital": 21000.0, "max_profit": 320.0, "max_loss": 20680.0,
      "opened_at": "2026-09-18T22:01:31.477972+00:00", "status": "open",
      "closed_at": null, "close_price": null, "realized_pnl": null,
      "unrealized_pnl": 176.0, "mark": 144.0,
      "underlying_price_at_open": 225.0, "underlying_mark": 225.0,
      "dte": 32, "expiry": null, "notes": "demo CSP", "credit_debit": "credit",
      "fill_id": "cfe95aa7-9f7c-4887-b979-7e44ee98381c",
      "is_template": false, "target_delta": null
    },
    {
      "id": "cb2c4fc6-36a0-4b17-8ebf-0b084fddea97",
      "underlying": "MSFT",
      "strategy": "bull_put_spread",
      "legs": [
        {"symbol": "MSFT", "option_type": "put", "strike": 400.0, "dte": 28, "side": "sell", "quantity": 1, "delta": -0.25},
        {"symbol": "MSFT", "option_type": "put", "strike": 390.0, "dte": 28, "side": "buy", "quantity": 1, "delta": -0.12}
      ],
      "credit": 185.0, "capital": 1000.0, "max_profit": 185.0, "max_loss": 815.0,
      "opened_at": "2026-09-18T22:01:31.478252+00:00", "status": "open",
      "closed_at": null, "close_price": null, "realized_pnl": null,
      "unrealized_pnl": 111.0, "mark": 74.0,
      "underlying_price_at_open": 420.0, "underlying_mark": 420.0,
      "dte": 28, "expiry": null, "notes": "demo bull put", "credit_debit": "credit",
      "fill_id": "e69d4f58-ad25-457d-aa43-a14cf8b7ca26",
      "is_template": false, "target_delta": null
    },
    {
      "id": "c93d736a-5c5f-459b-8d59-62b9e2042b63",
      "underlying": "SPY",
      "strategy": "iron_condor",
      "legs": [
        {"symbol": "SPY", "option_type": "put", "strike": 520.0, "dte": 25, "side": "buy", "quantity": 1, "delta": -0.08},
        {"symbol": "SPY", "option_type": "put", "strike": 530.0, "dte": 25, "side": "sell", "quantity": 1, "delta": -0.16},
        {"symbol": "SPY", "option_type": "call", "strike": 560.0, "dte": 25, "side": "sell", "quantity": 1, "delta": 0.16},
        {"symbol": "SPY", "option_type": "call", "strike": 570.0, "dte": 25, "side": "buy", "quantity": 1, "delta": 0.08}
      ],
      "credit": 140.0, "capital": 1000.0, "max_profit": 140.0, "max_loss": 860.0,
      "opened_at": "2026-09-18T22:01:31.478694+00:00", "status": "open",
      "closed_at": null, "close_price": null, "realized_pnl": null,
      "unrealized_pnl": 70.0, "mark": 70.0,
      "underlying_price_at_open": 545.0, "underlying_mark": 545.0,
      "dte": 25, "expiry": null, "notes": "demo iron condor", "credit_debit": "credit",
      "fill_id": "bdc73f2d-44b9-4ec7-8fe7-2b9eefa66d89",
      "is_template": false, "target_delta": null
    },
    {
      "id": "2960c59d-c1d4-40db-ba91-c3c41fc38db0",
      "underlying": "NVDA",
      "strategy": "covered_call",
      "legs": [{"symbol": "NVDA", "option_type": "call", "strike": 140.0, "dte": 21, "side": "sell", "quantity": 1, "delta": 0.28}],
      "credit": 210.0, "capital": 13000.0, "max_profit": 210.0, "max_loss": null,
      "opened_at": "2026-09-18T22:01:31.491627+00:00", "status": "open",
      "closed_at": null, "close_price": null, "realized_pnl": null,
      "unrealized_pnl": 84.0, "mark": 126.0,
      "underlying_price_at_open": 128.0, "underlying_mark": 128.0,
      "dte": 21, "expiry": null, "notes": "demo covered call", "credit_debit": "credit",
      "fill_id": "d4aeb7fd-dcaa-4cb8-b53b-26bb5dbb7e78",
      "is_template": false, "target_delta": null
    },
    {
      "id": "381b3d4b-5fe1-46e4-bb67-20bb06b24208",
      "underlying": "AMD",
      "strategy": "bear_call_spread",
      "legs": [
        {"symbol": "AMD", "option_type": "call", "strike": 170.0, "dte": 30, "side": "sell", "quantity": 1, "delta": 0.24},
        {"symbol": "AMD", "option_type": "call", "strike": 175.0, "dte": 30, "side": "buy", "quantity": 1, "delta": 0.14}
      ],
      "credit": 95.0, "capital": 500.0, "max_profit": 95.0, "max_loss": 405.0,
      "opened_at": "2026-09-18T22:01:31.503165+00:00", "status": "open",
      "closed_at": null, "close_price": null, "realized_pnl": null,
      "unrealized_pnl": 61.75, "mark": 33.25,
      "underlying_price_at_open": 158.0, "underlying_mark": 158.0,
      "dte": 30, "expiry": null, "notes": "demo bear call", "credit_debit": "credit",
      "fill_id": "4696a015-e65a-40d0-8baa-e10c2f673c91",
      "is_template": false, "target_delta": null
    }
  ],
  "fills": [
    {"id": "cfe95aa7-9f7c-4887-b979-7e44ee98381c", "type": "open", "strategy": "cash_secured_put", "underlying": "AAPL", "fill_price": 320.0, "position_id": "10077dba-c487-442e-8e69-4f37ce7fde08", "ts": "2026-09-18T22:01:31.477982+00:00", "demo": true},
    {"id": "e69d4f58-ad25-457d-aa43-a14cf8b7ca26", "type": "open", "strategy": "bull_put_spread", "underlying": "MSFT", "fill_price": 185.0, "position_id": "cb2c4fc6-36a0-4b17-8ebf-0b084fddea97", "ts": "2026-09-18T22:01:31.478258+00:00", "demo": true},
    {"id": "bdc73f2d-44b9-4ec7-8fe7-2b9eefa66d89", "type": "open", "strategy": "iron_condor", "underlying": "SPY", "fill_price": 140.0, "position_id": "c93d736a-5c5f-459b-8d59-62b9e2042b63", "ts": "2026-09-18T22:01:31.478701+00:00", "demo": true},
    {"id": "d4aeb7fd-dcaa-4cb8-b53b-26bb5dbb7e78", "type": "open", "strategy": "covered_call", "underlying": "NVDA", "fill_price": 210.0, "position_id": "2960c59d-c1d4-40db-ba91-c3c41fc38db0", "ts": "2026-09-18T22:01:31.491644+00:00", "demo": true},
    {"id": "4696a015-e65a-40d0-8baa-e10c2f673c91", "type": "open", "strategy": "bear_call_spread", "underlying": "AMD", "fill_price": 95.0, "position_id": "381b3d4b-5fe1-46e4-bb67-20bb06b24208", "ts": "2026-09-18T22:01:31.503178+00:00", "demo": true}
  ],
  "risk_events": [],
  "version": 2
}
SEED_EOF
  echo "seeded demo portfolio"
fi


# Auto-detect LAN IP for assistant Host allowlist + QR pair_url (phones on same Wi-Fi).
# Does not touch shared Caddy on :8080.
detect_lan_ip() {
  ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true
}
LAN_IP="${PULSE_LAN_IP:-$(detect_lan_ip)}"
if [ -n "${LAN_IP}" ]; then
  export PULSE_ALLOWED_HOSTS="${PULSE_ALLOWED_HOSTS:+$PULSE_ALLOWED_HOSTS,}${LAN_IP}"
  export PULSE_PUBLIC_HOST="${PULSE_PUBLIC_HOST:-http://${LAN_IP}:${PORT}/pulse}"
  echo "[pulse] LAN IP ${LAN_IP}"
  echo "[pulse] PULSE_ALLOWED_HOSTS=${PULSE_ALLOWED_HOSTS}"
  echo "[pulse] PULSE_PUBLIC_HOST=${PULSE_PUBLIC_HOST}"
else
  echo "[pulse] No LAN IP detected; set PULSE_ALLOWED_HOSTS / PULSE_PUBLIC_HOST if phones cannot pair."
fi
export PULSE_PUBLIC_HOST="${PULSE_PUBLIC_HOST:-http://127.0.0.1:${PORT}/pulse}"

echo "Starting Pulse backend on ${PULSE_HOST:-127.0.0.1}:$PORT ..."
exec "$VENV_DIR/bin/python" -m uvicorn main:app --host "${PULSE_HOST:-127.0.0.1}" --port "$PORT"
