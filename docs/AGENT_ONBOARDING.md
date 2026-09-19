# Agent onboarding — Project Money

Checklist for a **new coding agent** joining this repo.

1. Read [`BACKEND.md`](./BACKEND.md) end-to-end (backend-as-box model).
2. Read [`LIVE_URLS.md`](./LIVE_URLS.md) for current public bases; do not hardcode stale tunnels in PRs without updating that file.
3. Read `stock-data-scanner/LIVE_PROXY.md` — **Caddy owns :8080**.
4. Decide your lane:
   - **Client** (iOS / PWA / Android): consume `{BACKEND_BASE}/pulse/api/*` and/or `/api/scan`; do not spawn scanners on device.
   - **Backend / scanner**: change APIs under `options-seller/api` or `stock-data-scanner`; keep paper-trading guarantees.
5. Prefer small PRs. Coordinate with Project Money group bots (Robinhood, Stock Data Scanner, Celebrity Portfolio Scanner, Infra).
6. Assume an external ChatGPT agent may also edit source and relaunch UIs — prefer additive changes; don’t delete unknown panels without asking.
7. Smoke before claiming done:
   ```bash
   curl -sS "$BASE/pulse/api/health"
   curl -sS "$BASE/api/scan" | head -c 200
   ```
8. Never commit secrets. Tunnel URLs are fine in `LIVE_URLS.md`.

Done when your change has docs touch-ups if it alters the public contract.
