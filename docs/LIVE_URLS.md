# Live public URLs (ops)

> **Ephemeral:** Cloudflare quick tunnels change when `cloudflared` restarts.
> Update this file whenever tunnels are rotated. Clients (iOS `AppConfig.baseURL`)
> must match `BACKEND_BASE` below.

| Role | URL |
|------|-----|
| **BACKEND_BASE** (scan + Pulse via Caddy :8080) | `https://views-pill-radical-templates.trycloudflare.com` |
| Pulse API (clients) | `https://views-pill-radical-templates.trycloudflare.com/pulse` |
| Scan JSON | `https://views-pill-radical-templates.trycloudflare.com/api/scan` |
| Stock Data Scanner UI (Streamlit) | `https://views-pill-radical-templates.trycloudflare.com/` |
| Options Seller Command Center UI | `https://review-receptors-movies-provider.trycloudflare.com/` |

Last verified (UTC): 2026-09-19T02:23Z
