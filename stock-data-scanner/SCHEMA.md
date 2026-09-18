# Scan export schema — `stock-data-scanner.scan/v0.1`

Machine-readable contract for Robinhood (and other consumers). Written to
`scan-latest.json` on each dashboard refresh via `scan.write_scan()`.

## Envelope

```json
{
  "schema": "stock-data-scanner.scan/v0.1",
  "asOf": "2026-09-18T20:00:00Z",
  "source": "yahoo_finance",
  "universe": ["AAPL", "..."],
  "results": [ /* ScanResult[] */ ]
}
```

- `asOf` — ISO-8601 UTC timestamp of the scan
- `source` — always `"yahoo_finance"` for this exporter
- Missing numeric/string fields are **`null`** (never invented). UI may show "—".

## ScanResult (required fields)

| Field | Type | Notes |
|-------|------|--------|
| symbol | string | |
| name | string\|null | |
| price, change, changePct | number\|null | |
| previousClose, open, dayHigh, dayLow | number\|null | |
| volume, avgVolume, marketCap | number\|null | |
| bid, ask | number\|null | |
| sector, industry | string\|null | |
| pe, eps, beta, dividendYield | number\|null | |
| fiftyTwoWeekHigh, fiftyTwoWeekLow | number\|null | |
| trend | object | see below |
| liquidity | object | see below |
| earnings | object | see below |
| options | object | see below (MVP: mostly null) |
| markers | object | `{ available: string[], missing: string[] }` |

### trend

```json
{
  "bias": "bullish|bearish|neutral",
  "sma20": null,
  "sma50": null,
  "sma200": null,
  "priceVsSma50Pct": null
}
```

`bias` is derived simply from price vs SMA50 (±0.5% band → neutral).

### liquidity

```json
{ "volume": null, "avgVolume": null, "volumeRatio": null }
```

`volumeRatio = volume / avgVolume` when both present and avgVolume ≠ 0.

### earnings

```json
{ "nextDate": "YYYY-MM-DD"|null, "daysToEarnings": number|null }
```

From yfinance calendar when available.

### options (MVP)

```json
{
  "iv": null,
  "ivRank": null,
  "ivPercentile": null,
  "impliedMovePct": null,
  "suggested": null
}
```

All options fields may be `null` in this MVP.

#### Future: `options.suggested`

When populated, `suggested` will be an array of strategy legs (or a small
strategy object containing `legs`). **Each suggested leg must include:**

| Field | Type | Required |
|-------|------|----------|
| strike | number | yes |
| dte | number | yes (days to expiration) |
| delta | number\|null | planned |
| premium | number\|null | planned (debit/credit) |
| **bid** | number\|null | **required for Robinhood** |
| **ask** | number\|null | **required (or provide mid)** |
| mid | number\|null | optional if bid+ask present |
| **openInterest** | number\|null | **required for Robinhood** |
| right | "call"\|"put" | recommended |
| expiration | string (YYYY-MM-DD) | recommended |
| side | "buy"\|"sell" | recommended |

Do not invent bid/ask/OI — use `null` until a real options data source is wired.
