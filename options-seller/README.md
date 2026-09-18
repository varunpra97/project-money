# options-seller

Paper-trading **options selling** strategies driven by
[`stock-data-scanner.scan/v0.1`](../stock-data-scanner/SCHEMA.md) JSON.

**NOT FINANCIAL ADVICE.** Educational / research tooling only. This package
**never places live broker orders**. Use at your own risk.

## Strategies

| Module | Description |
|--------|-------------|
| `cash_secured_put` | Sell puts cash-secured |
| `covered_call` | Sell calls against long shares |
| `wheel` | State machine: CSP → assigned → CC → called away → CSP |
| `bull_put_credit_spread` | Defined-risk bullish credit put spread |
| `bear_call_credit_spread` | Defined-risk bearish credit call spread |
| `iron_condor` | Neutral short strangle with wings |

### Selector rules (high level)

1. Long shares (≥100) → covered call (or continue wheel)
2. Active wheel state for symbol → continue wheel
3. Bullish + IV ok + cash → CSP (or bull put if defined-risk / low cash)
4. Mildly bearish + high IV → bear call spread
5. Neutral + high IV → iron condor
6. Mildly bullish defined-risk → bull put spread

Earnings within 7 days (when `earnings.daysToEarnings` present) → skip.

### Null options handling

Scanner MVP often has `options.*` as `null`. This package **never invents**
IV/bid/ask/OI. When `options.suggested` is absent, builders emit **plan
templates** with target DTE/delta and approximate strikes. When `suggested`
legs are present (with quotes), builders produce concrete `OrderPlan`s.

## Scanner schema

Envelope: `schema`, `asOf`, `source`, `universe`, `results[]`.

See `/workspace/stock-data-scanner/SCHEMA.md` for the locked contract.

Live export path: `/workspace/stock-data-scanner/scan-latest.json`  
Snapshot copy: `examples/scan-latest.json`

Portfolio / capital context is a **separate** JSON (not part of the scan):

```json
{
  "cash_available": 75000,
  "prefer_defined_risk": false,
  "positions": [
    {"symbol": "AAPL", "shares_owned": 100, "has_shares": true},
    {"symbol": "XYZ", "shares_owned": 100, "wheel_state": "assigned"}
  ]
}
```

## Install

```bash
cd /workspace/options-seller
pip install -e ".[dev]"
```

## CLI

```bash
options-seller strategies list

# Live scanner export (default workflow)
options-seller scan run --input /workspace/stock-data-scanner/scan-latest.json

# With portfolio context + example fixtures
options-seller scan run \
  --input examples/sample_scan.json \
  --portfolio examples/portfolio.json
```

Paper fills persist to `data/paper_portfolio.json` (or `--store`). Templates are
recorded as `template_only` / `planned` positions (no premium) until quotes exist.

```bash
options-seller paper status
options-seller paper close <id>
options-seller paper seed
```

## Shared defaults

Configured in `src/options_seller/config/defaults.yaml`:

- DTE 21–45 (prefer 30–45 CSP/CC; 20–45 spreads)
- Short delta ~0.15–0.30 (default 0.20–0.25; iron condor ~0.16)
- IV rank ≥ 30 when present
- Liquidity filters (min OI, max bid-ask) when quotes exist
- Credit spreads: target credit ≈ 1/3 width; max loss = width − credit

## Tests

```bash
pytest
```



## Dashboard (Command Center)

Streamlit paper-trading UI inspired by tastytrade / thinkorswim Analyze / OptionTracker —
**not** a generic stock chart page.

```bash
cd /workspace/options-seller
pip install -e ".[dev]"
streamlit run dashboard/app.py --server.port 8502 --server.address 0.0.0.0
```

- **URL / port:** prefer `http://0.0.0.0:8502` (away from scanner UI on 8501).
  On this shared box **8502 may host the scanner JSON API** — if so run on **8503**.
  Current run: `http://0.0.0.0:8503`.
- Clear **PAPER / NOT LIVE** banner on every load.
- Tabs: Positions · Activity · Candidates · Risk (payoff @ expiry) · Income.
- Sidebar: Seed demo book, scan→paper dry-run, reset, slippage, portfolio path.

### Scanner wiring

| Env | Purpose |
|-----|---------|
| `SCANNER_BASE_URL` | `https://views-pill-radical-templates.trycloudflare.com` (UI + `/api/scan` + `/scan-latest.json` when reachable) |
| `SCANNER_UI_URL` | Browser link for “Open Stock Scanner” (defaults to `SCANNER_BASE_URL`) |
| `SCANNER_JSON_URL` | Explicit JSON URL (overrides base-derived paths) |
| `SCANNER_JSON_PATH` | Local file primary fallback (default `/workspace/stock-data-scanner/scan-latest.json`) |

On-box **local file is primary** (`/workspace/stock-data-scanner/scan-latest.json`).
Remote is best-effort (IPv4/`curl -4`); NXDOMAIN is not an error banner.

Remote JSON paths when `SCANNER_BASE_URL` is reachable:

- `{BASE}/scan-latest.json`
- `{BASE}/api/scan`

If remote returns HTML (Streamlit UI) or fails, the dashboard falls back to the **local
file** (rewritten when the scanner refreshes on the same box), then `examples/scan-latest.json`.

The dashboard status strip shows Scanner UI link, data `asOf`, and remote/local OK flags.

### Paper portfolio API

Importable helpers (used by the dashboard):

- `summary_metrics()`, `list_open()`, `list_closed()`, `list_fills()`
- `portfolio_greeks_est()` — always labeled **EST.** (never invents live IV/greeks precision)
- `seed_demo_book()` — opens realistic synthetic credits so charts are not empty
- `close_position(id, price=None)` → realized PnL

Persist path: `data/paper_portfolio.json`.

## Disclaimer

**NOT FINANCIAL ADVICE.** Options involve substantial risk of loss and are not
suitable for all investors. Paper / dry-run only — no live brokerage APIs.
