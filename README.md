# Project Money

Paper-trading options insights stack: **stock scanners + Pulse API backend** on a shared Linux box, with **iOS / PWA** clients.

> **Backend server:** the Grok Bot machine running scanners is the canonical API host.
> Clients call HTTPS → Caddy → Pulse (`/pulse`) and scan (`/api/scan`).
> Full contract: **[docs/BACKEND.md](docs/BACKEND.md)** · Onboarding: **[docs/AGENT_ONBOARDING.md](docs/AGENT_ONBOARDING.md)** · Live URLs: **[docs/LIVE_URLS.md](docs/LIVE_URLS.md)**

## Layout

| Path | What |
|------|------|
| `stock-data-scanner/` | Universe scan, celebrity priority, JSON `/api/scan`, Caddy proxy |
| `options-seller/` | Paper options strategies, Command Center, **Pulse FastAPI** (`api/`) |
| `mobile-app/` | Pulse PWA |
| `ios-app/` | Native SwiftUI Pulse |
| `docs/` | Agent-facing backend + ops docs |

## Quick links

- Windows/macOS setup and agent commands: [Run the server](docs/RUN_SERVER.md)
- Pulse health: `{BACKEND_BASE}/pulse/api/health`
- Scan feed: `{BACKEND_BASE}/api/scan` (schema `stock-data-scanner.scan/v0.1`)
- Risk: `{BACKEND_BASE}/pulse/api/risk/status` ($50k hard cap, paper)
- OpenAPI (on box): `http://127.0.0.1:8504/docs`

## Hard ops rules

1. Port **8080 = Caddy only** (`stock-data-scanner/LIVE_PROXY.md`).
2. Paper trading only unless a human explicitly asks for live brokerage.
3. Prefer PRs / small commits; coordinate with Project Money bots.

## License

MIT (see package metadata under subprojects).
