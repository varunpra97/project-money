# Live public proxy — LOCKED

- **Hostname:** https://views-pill-radical-templates.trycloudflare.com
- **Live:** Caddy on `:8080` (`Caddyfile`)
- **Watchdog:** `bin/keep-caddy-alive.sh`
- **Do not** start `proxy_server.py` on `:8080` (causes 502 flaps)
- Backends: Streamlit `:8501`, JSON `:8502`
- Tunnel: cloudflared → `http://127.0.0.1:8080`

## Static assets (2026-09-18)

- `/static/*` is served from the Streamlit package static dir via `file_server` (not reverse-proxied).
- Real hashed chunks → `200` + `text/javascript` + long `Cache-Control`.
- Missing / stale hashes → `404` + `application/javascript` + `no-cache` (never SPA `text/html`).
- HTML `/` → `Cache-Control: no-cache` via reverse_proxy to Streamlit.
- Prefer `caddy reload` over kill/restart so the tunnel hostname stays stable.
