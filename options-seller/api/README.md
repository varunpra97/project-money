# Mobile Trading-Insights API

FastAPI backend for the mobile app. **Paper trading / educational only** — it
reads the same paper portfolio store and scan data as the Streamlit dashboard
and exposes it as low-latency JSON. It never places live orders.

## Run

```bash
./api/run.sh          # starts uvicorn on http://127.0.0.1:8504
```

Interactive docs: `http://127.0.0.1:8504/docs`

## Caching (low latency)

- In-memory TTL cache per endpoint; cached responses return in <50ms.
- Portfolio endpoints: 30s · candidates: 60s · celebrity: 5m ·
  earnings/volatility: 10m (backed by `market_signals`' own 6h Yahoo cache —
  Yahoo is never hammered).
- Quotes: 60s for `1d`, 15m for `5d/1mo/3mo/1y`.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | `{"ok": true}` |
| GET | `/api/portfolio/summary` | account_value, buying_power, day_pnl, day_pnl_pct, total_pnl, open_positions, greeks{delta,theta,gamma,vega,estimated}, as_of |
| GET | `/api/portfolio/positions` | open positions: id, underlying, strategy, display_name, opened_at, dte, qty, credit, unrealized, pct_of_max_profit, days_held, risk_label |
| GET | `/api/portfolio/activity` | fills/closes newest-first (limit 50): ts, kind, text, amount |
| GET | `/api/insights/celebrity` | tracker moves + live prices from scan envelope: scan_date, moves[{rank,symbol,company,investor,what_changed,period,why,heat,live_price,live_chg_pct}] |
| GET | `/api/insights/earnings` | as_of, fresh, rows[{symbol,company,earnings_date,when,status}] sorted by upcoming date |
| GET | `/api/insights/volatility` | as_of, fresh, rows[{symbol,company,last,chg_1d_pct,chg_5d_pct,vol_20d_ann_pct,max_1d_move_10d_pct,atr14_pct,volatile,reasons[]}] sorted by biggest 10d move |
| GET | `/api/candidates` | top 20 scan candidates: symbol, company, strategy, display_name, dte, bias, credit_status (quoted/template), rationale, skip_reason |
| GET | `/api/quote/{symbol}?range=` | range = 1d\|5d\|1mo\|3mo\|1y → symbol, price, chg_pct, bars[{t: unix_ts, c: close}] |
| GET | `/` | serves the SPA from `../mobile-app/dist` when built; otherwise a JSON note |

Money is returned as JSON **numbers** (rounded to 2dp), never strings.

## Errors

Handlers never 500 on missing data — they return HTTP 200 with
`{"error": "<message>"}` so the mobile client can show a graceful state.

## risk_label

Heuristic on open positions: `max_loss <= 0` → `none`; `max_loss/credit`
< 3 → `low`; < 10 → `moderate`; else `high` (or `high` when credit ≤ 0).
