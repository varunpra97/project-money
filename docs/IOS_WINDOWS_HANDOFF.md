# Windows backend / iOS coordination

The Windows agent owns Windows deployment and host-specific configuration.
The Mac agent owns native iOS builds. Both use the shared Python backend and
must fetch/rebase before pushing main. See [Run the server](RUN_SERVER.md) for
collection, persistent storage, checks and startup commands.

## Contract used by the current iOS and web builds

- The configured backend base includes `/pulse` when served through Caddy.
  JSON paths also work without that prefix when connecting to Pulse directly.
- Quote bars require `t` (Unix seconds), `o`, `h`, `l`, `c`, and `v`.
  Keep `source`, `as_of`, cache freshness fields and all five quote ranges.
- `/api/live/events?symbols=...` uses SSE with `quotes[]` and `sent_at`.
  Each quote includes provider timestamp, received timestamp, state and source.
  HTTP fallback bars must not be described as exchange-live ticks.
- `/api/portfolio/positions` returns `positions[]`. Keep `legs[]` with side,
  type, strike, quantity and expiry. `expiry` is the shared date, or null when
  missing/multiple. Each leg retains its own recorded date.
- Position `opening_value` and `close_value` are **total dollars for the
  position**, not per-share premiums. `premium_direction` is credit/debit.
  `equity` is signed net option value (short liabilities are negative).
  `unrealized` is the recorded net P&L, `return_pct` uses opening premium as its
  denominator, and `day_pnl` stays null without a prior-day option-mark baseline.
  `mark_as_of` is null for old records with no mark timestamp; do not invent one.
- Performance uses lifetime and trailing 7/30/90 days; unknown period P&L is
  null. News supplies attributed headlines and separate editorial product ideas.
- Historical scanners use `/api/history/scanners`, `/run` and `/jobs/{id}`.
  Preserve error/warning details and `bars_scanned`; zero matches can be valid.
- Assistant requests need the paired token and `X-Pulse-Assistant: 1`.
  The runtime/sign-in, conversations and source checkout must be on the server.
  Pairing/bootstrap must not be exposed by an unauthenticated public proxy.

## Information needed from the Windows agent

Record the reachable Pulse base URL and any changed endpoint/schema contracts
here or in the agreed task handoff before asking for an iOS rebuild. Include
commit SHA, migration needs, data-check results, streaming/proxy behavior and
assistant availability. Keep passwords, keys and access tokens out of Git.

The Mac has verified Windows CI, not the VarunPC deployment. The current native
base address is in `ios-app/Pulse/Config.swift`; switching that build to Windows
requires a verified reachable backend address. Do not change it to an untested
host solely because the host responds to Tailscale ping.
