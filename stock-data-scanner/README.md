# Stock Data Scanner

Dark-themed Streamlit dashboard that fetches live stock data from Yahoo Finance
via `yfinance` (no API keys) and exports a machine-readable scan for Robinhood.

## Features

- Default watchlist (Celebrity Portfolio priority + anchors): SPCX, AMZN, GOOGL, NFLX, META, CBRS, HD, INTC, UBER, VST, TEM, BE, FDXF, V, MA, SPGI, AVGO, SPY, QQQ
- Overview cards/table: last price, change $, change %, volume, market cap, day high/low, previous close (green/red)
- Ticker detail: PE, EPS, 52w high/low, beta, dividend yield, avg volume, sector/industry, open, bid/ask, trend/SMA, earnings
- Price chart with period toggles: 1d, 5d, 1mo, 3mo, 1y
- Manual refresh + optional auto-refresh (~60s)
- On each refresh, writes `scan-latest.json` (`stock-data-scanner.scan/v0.1`) — see `SCHEMA.md`

## Setup

```bash
cd /workspace/stock-data-scanner
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the dashboard

```bash
cd /workspace/stock-data-scanner
source .venv/bin/activate
streamlit run app.py --server.headless true --server.port 8501
```

Open http://localhost:8501

## Smoke test (no long-lived server)

```bash
cd /workspace/stock-data-scanner
source .venv/bin/activate
python smoke_test.py
```

This fetches 1–2 tickers, writes `scan-latest.json`, and prints sample prices.

## Scan export

- File: `scan-latest.json` (project root)
- Schema id: `stock-data-scanner.scan/v0.1`
- Details / future `options.suggested` leg shape: [`SCHEMA.md`](SCHEMA.md)

## Public JSON API (for Robinhood / pollers)

A small JSON server + reverse proxy expose the same scan envelope as
`application/json` on the same host as the dashboard:

| URL | Upstream |
|-----|----------|
| `GET /api/scan` | JSON (`scan-latest.json`) |
| `GET /api/scan/` | JSON |
| `GET /scan-latest.json` | JSON |
| everything else | Streamlit dashboard |

```bash
# Terminal A — dashboard (8501)
source .venv/bin/activate
streamlit run app.py --server.headless true --server.port 8501

# Terminal B — JSON API (8502)
python json_api_server.py

# Terminal C — reverse proxy (8080)
python proxy_server.py

# Terminal D — Cloudflare quick tunnel (points at proxy, not Streamlit)
/tmp/cloudflared tunnel --url http://127.0.0.1:8080 --no-autoupdate
```

Open the trycloudflare.com URL printed by cloudflared. Poll
`https://<tunnel>/api/scan` for the scan envelope (`Content-Type: application/json`,
CORS `*`). If the file is missing, the API returns `404 {"error":"scan not ready"}`.

## Known issues

- Yahoo Finance sometimes returns HTTP 429 (crumb rate-limit) or 401 on the
  `quoteSummary` / `.info` endpoint. The scanner falls back to `fast_info` +
  price history for quotes, OHLC, volume, market cap, and 52-week range.
  Fundamentals that only live on `.info` (name, sector, industry, PE, EPS,
  beta, dividend yield, bid/ask, earnings calendar) may show as `null` / "—"
  until Yahoo accepts requests again. Numbers are never invented.
