# Pulse API (paper trading)

FastAPI backend for iOS / PWA / web clients. See **[docs/BACKEND.md](../../docs/BACKEND.md)**.

```bash
./run.sh   # 127.0.0.1:8504 — Caddy mounts this at /pulse
```

## Pulse web, iPhone and embedded assistant

From the repository root, run `bash start-pulse-backend.sh`, then open
http://localhost:8505/. Set `PULSE_HOST=0.0.0.0` so an
owned iPhone on the same trusted Wi-Fi can connect. Update `ios-app/Pulse/Config.swift`
if the Mac's LAN address changes; rebuild and Run the Pulse scheme in Xcode.
The script seeds demo paper positions only with `PULSE_SEED_DEMO=1` and no existing portfolio.
Saved paper marks are not live option quotes.

Stats includes lifetime and trailing 7/30/90-day views. Period P&L needs a
recorded opening snapshot; missing history is shown as unavailable, never
backfilled with invented trades. Snapshots are recorded while the server runs.
News reads Cboe, CNBC and Federal Reserve RSS, retains dated results on source
failures, and offers a manual refresh. Product ideas are editorial suggestions.
Ticker Search retrieves each requested symbol independently of watchlists.
Charts offer OHLC candlesticks/line, volume, SMA 20, EMA 20 and Bollinger Bands
(20 periods, 2 population standard deviations), zoom, history navigation and
bar inspection. Indicators need 20 bars and use the selected interval. Yahoo
Finance data can be delayed; this is not a guaranteed exchange-real-time feed or a
licensed TradingView terminal.

Run `bash setup-pulse-assistant.sh` once to install the pinned official Codex
runtime and use your existing ChatGPT login. On the Mac, open Assistant. On
iPhone, open Assistant and enter the code under **Connection & device pairing**
on the Mac. Pairing grants access to this repository and saved conversations.
The code expires after ten minutes. Keep this development server on a trusted
network; do not expose the assistant over a public tunnel. Add intended host
names with `PULSE_ALLOWED_HOSTS` only when needed.

The embedded chat is powered by Codex. It is a separate conversation from the
Codex desktop task. Ask mode can inspect app context and source; Edit app mode
can edit, test, commit, rebase and push the repository, with command approvals
shown in chat when requested. It cannot place trades. Frontend edits require
`npm --prefix mobile-app run build`; native changes require Xcode installation.
Backend changes require restart. Restarting the backend interrupts active chat
work. Conversations persist, but in-flight work does not resume automatically.
Credentials, pairing state, conversations, installed tooling and portfolio data
are excluded from Git. Never copy them into commits.


### Live prices and latency

`GET /api/live?symbols=AAPL,MSFT` returns latest dated quotes.
`GET /api/live/events?symbols=AAPL,MSFT` streams Server-Sent Events; both clients
use this push path with automatic reconnect. The backend shares one Yahoo
WebSocket subscription set, follows paper-position underlyings and requested
symbols, and falls back to minute-bar HTTP checks every 20 seconds when updates
stop. Candle history refreshes every 20 seconds independently. Saved option
marks/Greeks are not relabelled live. A quiet or closed market shows the source
age and last available price. Caddy flushes SSE immediately; disable buffering
in any additional Windows proxy. This implementation uses portable asyncio
and passes the Windows/macOS CI checks. The intended Windows server deployment remains unverified.

Run the real TCP integration benchmark from `options-seller`:

```bash
PYTHONPATH=src:. api/.venv-pulse/bin/python -m unittest discover -s tests/integration -p test_live_latency.py -v
```

It checks 100 ordered ticks across three clients, concurrent blocking provider
work off the event loop, reconnect snapshots, invalid ticks, and stale labels.
Local reference run: p50 2.00 ms, p95 2.49 ms, max 3.36 ms. Regression budgets:
p95 <250 ms and max <1 s to allow CI overhead. These numbers exclude provider
latency, public proxy/WAN/Wi-Fi, and native rendering. In-app delivery estimates
use server/device clocks and are approximate. Next deployment checks should
measure Windows-to-client p50/p95 and clock offset with a licensed live source.
