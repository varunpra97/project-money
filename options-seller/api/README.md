# Pulse API (paper trading)

FastAPI backend for iOS / PWA / web clients. See **[docs/BACKEND.md](../../docs/BACKEND.md)**.

```bash
./run.sh   # 127.0.0.1:8504 — Caddy mounts this at /pulse
```

## Pulse web, iPhone and embedded assistant

From the repository root, run `bash start-pulse-backend.sh`, then open
http://localhost:8505/. The server binds to the Mac's network interface so an
owned iPhone on the same trusted Wi-Fi can connect. Update `ios-app/Pulse/Config.swift`
if the Mac's LAN address changes; rebuild and Run the Pulse scheme in Xcode.
The script seeds explicitly demo paper positions only when no portfolio exists.
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
Finance data can be delayed; this is not an exchange streaming feed or a
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
