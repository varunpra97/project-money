# Pulse — Paper Options-Trading Companion

**Pulse** is a Robinhood-style native iOS app (SwiftUI, iOS 17+) for paper-trading
options-selling strategies — cash-secured puts, credit spreads, iron condors, and the
wheel — backed by a Python FastAPI server. It scans the market for high-IV,
option-selling candidates, shows live option chains with Greeks, and recommends
credit-spread strikes around two weeks to expiration.

> **Paper trading only.** Nothing here places real orders. All positions, P&L, and
> Greeks are simulated for education and strategy research.

**Live backend:** `https://pulse-backend-jiar.onrender.com/pulse`
(iOS app → `ios-app/Pulse/Config.swift` → `AppConfig.baseURL`)

---

## iOS app

Tabs in the main app:

| Tab | What it shows |
|-----|---------------|
| **Home** | Portfolio summary (equity, buying power, day P&L), open positions with live Greeks. Tapping a position expands it: legs, **credit collected vs max risk** with a ratio bar and risk/reward, max profit/loss, breakeven, win probability. |
| **Stats** | Performance analytics — win rate, P&L over time, strategy breakdown. |
| **News** | Market news feed. |
| **Discover** | Option-selling candidates ranked by the backend (`/api/candidates`). |
| **Search** | Symbol lookup: live price chart (line/candles, ranges), quote, Greeks, options. |
| **Scanners** | Historical scanner runs. |
| **Activity** | Trade activity feed — opens, closes, expirations, assignments. |

### Scanner output

The Scanner (reached from Discover/candidates) lists the latest scan ranked by
**wheel rank**, **IV rank**, and biggest movers. Opening a result shows:

- **Scan** — strategy signal, ranking, price/volume/IV stats from `/api/scan`
- **Volatility · ThetaHedge** — option-selling attractiveness score, IV rank, expected move
- **Options pricing** — live option chain for the ~14-DTE expiration (bid/ask/last, IV, volume, open interest), served by the backend
- **Greeks** — delta, theta, gamma, vega per contract (Black-Scholes from contract IV)
- **🎯 Credit spread · ~14 DTE** — recommended put credit spread (bullish/neutral) or call credit spread (bearish): sell/buy strikes, width, expiration, short-leg delta, estimated credit, max profit/loss, breakeven, estimated win probability

### Position details

Expanding any position shows **Credit collected vs Max risk**: the premium received,
the maximum loss (from the backend, or computed from the legs when absent — spread
width minus credit, or strike × 100 × contracts minus credit for cash-secured puts),
a green/red ratio bar, and the risk/reward ratio. Debit positions show "Debit paid"
instead. Unlimited-risk positions (e.g. naked calls) say so explicitly.

---

## Backend API (FastAPI)

`options-seller/api/main.py`, served under `/pulse`. Hosted on Render (Docker, free
tier — first request after idle can take ~30–60s to wake).

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check |
| `GET /api/data/status` | Data freshness across feeds |
| `GET /api/scan` | Latest market scan (19 results), merged with ThetaHedge rows |
| `GET /api/candidates` | Ranked option-selling candidates |
| `GET /api/thetahedge?limit=` | ThetaHedge volatility rankings (1,300+ rows) |
| `POST /api/thetahedge/refresh` | Trigger a ThetaHedge recollect (15-min cooldown) |
| `GET /api/options/{symbol}?dte=14` | Option chain: 3 expirations nearest `dte`, strikes ±30% of spot — spot, bid/ask/last, IV, volume, OI. Via yfinance with a CBOE delayed-quotes fallback |
| `GET /api/quote/{symbol}?range=1d` | Live quote + chart data |
| `GET /api/symbol/{symbol}` | Symbol detail: volatility, earnings, Greeks |
| `GET /api/portfolio/summary` | Portfolio equity, buying power, P&L |
| `GET /api/portfolio/positions` | Open positions incl. legs, Greeks, `max_loss` / `max_profit`, credit |
| `GET /api/portfolio/activity` | Trade activity feed |
| `GET /api/insights/celebrity` | Celebrity-trader signal insights |
| `GET /api/insights/earnings` | Upcoming earnings for watched symbols |
| `GET /api/insights/volatility` | Volatility insights |
| `GET /api/performance` | Strategy performance stats |
| `GET /api/news` | Market news |
| `GET /api/risk/status` | Paper risk limits ($50k hard cap) |

### Data sources

- **Yahoo Finance** (via `yfinance`) — quotes, charts, and option chains. Yahoo's
  options API blocks some datacenter IPs, so `/api/options` falls back to…
- **CBOE delayed quotes** (`cdn.cboe.com`, public, no auth) — 15-minute delayed
  option chains parsed from OCC symbols into the same response shape.
- **ThetaHedge** (`app.thetahedge.io`) — volatility / option-selling attractiveness
  rankings, collected hourly by `thetahedge.py`. Note: its API silently returns
  `[]` for `limit_val >= 75`, so the collector pages at 50 with adaptive halving.

---

## Repo layout

| Path | What |
|------|------|
| `ios-app/` | Native SwiftUI Pulse app (`Pulse/` sources, `Pulse.xcodeproj`) |
| `options-seller/api/` | Pulse FastAPI backend (`main.py` + feed modules) |
| `options-seller/dashboard/` | Streamlit Command Center (human web UI) |
| `options-seller/src/` | Paper-trading engine (strategies, portfolio, risk) |
| `stock-data-scanner/` | Market universe scanner feeding `/api/scan` |
| `mobile-app/` | Pulse PWA client |
| `docs/` | Agent-facing backend contract + ops docs |
| `Dockerfile`, `render.yaml` | Render deploy (Docker, seeds demo portfolio on first boot) |

The Docker image seeds `/data/paper_portfolio.json` from
`options-seller/api/seed_portfolio.json` on first boot, so the app opens with 5
demo positions (AAPL cash-secured put, MSFT bull put spread, SPY iron condor, NVDA
covered call, AMD bear call spread). Demo data — not real holdings.

## Development

**Backend (local):**
```bash
cd options-seller/api
pip install -r requirements.txt
uvicorn main:app --port 8504   # app serves under /pulse
```

**iOS:** open `ios-app/Pulse.xcodeproj` in Xcode, set `AppConfig.baseURL`
(`Pulse/Config.swift`, or `PULSE_BACKEND_URL` in the scheme environment), build &
run on a device. Linux can't compile Swift — builds happen on a Mac.

**Deploy:** push to `main` → Render auto-deploys the Docker image.

## Docs

- Backend contract: [docs/BACKEND.md](docs/BACKEND.md)
- Run the server (Windows/macOS): [docs/RUN_SERVER.md](docs/RUN_SERVER.md)
- Agent onboarding: [docs/AGENT_ONBOARDING.md](docs/AGENT_ONBOARDING.md)

## License

MIT (see package metadata under subprojects).
