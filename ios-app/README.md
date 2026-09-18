# Pulse — native iOS app

Robinhood-style dark trading insights app (SwiftUI, iOS 17+). Four tabs — **Home**, **Discover**, **Search**, **Activity** — powered by the Pulse JSON API (`../options-seller/api/`). Paper-trading / educational context only; the app never places orders.

## What you need

- A Mac with **Xcode 16+** and an Apple ID signed in
- The Pulse API running somewhere reachable (the FastAPI backend in `../options-seller/api/`, exposed via a public URL, e.g. a Cloudflare tunnel). Note: tunnel URLs change when the backend restarts.

## Run it on your iPhone

1. Copy this folder to your Mac (or `git pull` — it's committed in the repo) and double-click **`Pulse.xcodeproj`**.
2. In the project navigator select **Pulse** (top item) → **Signing & Capabilities** → pick your **Team**. (Bundle ID is `com.pulse.app`; change it if Xcode complains it's taken.)
3. Open **`Pulse/Config.swift`** and set `AppConfig.baseURL` to your API's public URL, e.g.:
   ```swift
   static let baseURL = "https://your-tunnel.trycloudflare.com"
   ```
   No trailing slash. If you leave it empty, the app shows a setup screen instead of crashing.
4. Select your iPhone as the run destination (top toolbar) and press **Cmd+R**.

The first launch needs the phone unlocked and, on iOS 17+, Settings → General → VPN & Device Management → trust your developer certificate.

## API contract

All `GET`, money as JSON numbers. The app decodes with explicit `CodingKeys`, so field names must match exactly:

| Endpoint | Shape |
|---|---|
| `/api/health` | `{"ok": true}` |
| `/api/portfolio/summary` | `{account_value, buying_power, day_pnl, day_pnl_pct, total_pnl, open_positions, greeks{}, as_of}` |
| `/api/portfolio/positions` | `[{id, underlying, strategy, display_name, opened_at, dte, qty, credit, unrealized, pct_of_max_profit, days_held, risk_label}]` |
| `/api/portfolio/activity` | `[{ts, kind, text, amount}]` newest first |
| `/api/insights/celebrity` | `{scan_date, moves: [{rank, symbol, company, investor, what_changed, period, why, heat, live_price, live_chg_pct}]}` |
| `/api/insights/earnings` | `{as_of, fresh, rows: [{symbol, company, earnings_date, when, status}]}` |
| `/api/insights/volatility` | `{as_of, fresh, rows: [{symbol, company, last, chg_1d_pct, chg_5d_pct, vol_20d_ann_pct, max_1d_move_10d_pct, atr14_pct, volatile, reasons[]}]}` |
| `/api/candidates` | `[{symbol, company, strategy, display_name, dte, bias, credit_status, rationale}]` |
| `/api/quote/{symbol}?range=1d\|5d\|1mo\|3mo\|1y` | `{symbol, price, chg_pct, bars: [{t, c}]}` (`t` = unix seconds) |

Every screen handles API failure gracefully (error card + retry, never a blank screen) and most fields are optional in the models, so a slightly different backend won't hard-crash the app.

## Notes

- **Latency:** the API client caches aggressively in memory (30s portfolio, 5min insights, 60s intraday quotes) on top of `URLCache`; charts use Swift Charts with a drag-to-scrub crosshair.
- **App icon:** `Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png` is included (green pulse glyph on black); Xcode slices all required sizes from it automatically.
- **TestFlight:** Product → Archive → Distribute App → TestFlight. `ITSAppUsesNonExemptEncryption` is already set to `false` in Info.plist.

## Project layout

```
Pulse.xcodeproj/          hand-written, one app target
Pulse/
  PulseApp.swift          @main + tab bar + first-run setup screen
  Config.swift            ← set your API URL here
  Models.swift            Codable models (explicit CodingKeys)
  APIClient.swift         async/await client with in-memory TTL cache
  Components/
    Theme.swift           brand colors, card style, pills, error card
    Formatters.swift      money/percent/date helpers
    PriceChart.swift      Swift Charts line chart + range picker
  Views/
    HomeView.swift        account value, scrub chart, expandable positions
    DiscoverView.swift    celebrity moves, earnings radar, volatility, candidates
    SearchView.swift      symbol lookup + quote + stats + flags
    ActivityView.swift    feed + account stats
  Assets.xcassets/        AppIcon (1024px included)
  Info.plist
```

Built on Linux without compiling — please report any build warnings; the code was carefully reviewed against the iOS 17 SwiftUI/Charts APIs.
