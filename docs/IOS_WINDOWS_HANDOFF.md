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

## September 19: Windows handoff applied on Mac

The native Debug, Release and simulator default is now
`https://varunpc.tail68d841.ts.net/pulse`. Every ordinary request reaches Windows;
client URLCache and the old in-memory TTL cache are disabled. A scheme may set
`PULSE_BACKEND_URL` explicitly for isolated development. Keep Tailscale connected.
No Mac LAN address or temporary Cloudflare hostname is a build default.

The Windows source snapshot was based on `156be2e` with uncommitted changes.
Only its Config/APIClient changes were merged, preserving the newer Mac views
and position contracts. The Windows owner must merge their local backend work
with main; do not overwrite that checkout from this iOS patch.

Verified using Xcode 27.0 (27A266a): signed Debug build and USB installation on
the attached iPhone 17 Pro succeeded, preserving the app container and Keychain.
The user confirmed Home loads on that physical phone. The production Swift API
client decoded Windows health, summary, positions, activity, Discover and all
five AAPL OHLCV chart ranges. HTTPS SSE delivered dated `state: stale` prices and
reconnected after closing/reopening its connection; initial cached price events
were 21–39 ms from this Mac. That is a transport observation, not exchange-to-phone
latency. Xcode's physical screen viewer requires iOS 27 while this phone runs iOS 26.6.2; background/foreground and
cellular transitions on the physical phone are not yet independently verified.

Quotes show provider market time separately from cache age. SSE honors `as_of`,
`timestamp` and `state`; dated marks and curated filings stay labeled. News checks
Windows every minute while active. Home refreshes portfolio and charts every
20 seconds, retaining the last dated display on refresh failure.

## Assistant blocker requiring Windows action

The phone has successfully paired and received `/api/assistant/status`, but the
Windows backend responds `ready:false`. In the handed-off `api/assistant.py`,
`Bridge.ensure()` raises immediately when `PULSE_REQUIRE_DESKTOP_SESSION=1`;
there is no connection attempt in that branch. This is not an iPhone networking
or pairing failure. Native UI now distinguishes server connectivity from
assistant availability, preserves the draft during retry, and rechecks readiness when Send is tapped. An unavailable response is shown
beside the composer; no message POST occurs and the draft is retained.

The Windows owner should establish an authenticated connection to the **existing
running desktop process and requested task**, then verify a prompt and streamed
reply in that same task. Do not clear the flag, launch a replacement app-server,
or create a new conversation as a workaround. Keep local bootstrap local and
paired credentials in Keychain; no credentials belong in this file.

Please return `code: "desktop_transport_unavailable"` alongside the existing
`ready:false` and explanatory `message` while blocked. The client supports that
optional field and the existing message. When transport is available, retrying
status enables the native composer without reinstalling the app.

The Mac task's tool inventory currently exposes only its local host. Replies to
the Windows task failed both without a host and with the Windows-suggested
`remote-control` host (no registered host manager). The Windows agent can read
this handoff and the Mac task checkpoint using its established inbound route.
A working Mac-to-VarunPC desktop connection is needed for direct replies.

Official references: [App Server](https://learn.chatgpt.com/docs/app-server) and
[Remote connections](https://learn.chatgpt.com/docs/remote-connections). The
protocol documents transport and thread operations; it does not establish that
this Windows desktop process currently exposes a usable shared endpoint.

## Portfolio migration remains separate

Windows reported an empty paper store. The Mac checkout contains five open
positions and five fills, all explicitly marked as demo records. An exact
private copy was preserved outside Git; the source was not modified. This is
not yet an authoritative user portfolio and must not be imported automatically.
The previous Cloudflare backend also returns five positions, but their IDs and
strategy sets differ from the Mac store. Check that backend's original store and provenance before migration;
do not reconstruct balances from display responses or seed sample positions.

## Native client checks

```bash
xcrun swiftc -parse-as-library ios-app/Pulse/Config.swift ios-app/Pulse/Models.swift ios-app/Pulse/APIClient.swift ios-app/tests/ClientContractChecks.swift -o /tmp/pulse-client-contract
/tmp/pulse-client-contract
# Optional read-only integration check against the configured Windows server:
/tmp/pulse-client-contract --server
```

The offline checks verify fresh requests, HTTP versus decode error reporting,
freshness metadata and compatibility with older position responses. macOS CI
runs them without contacting the private Windows server.

## Product ideas → approved source changes

Both clients make idea titles and “Build this upgrade” actionable. Selecting one
opens its title, scope and evaluation measure in the assistant for review.
“Start upgrade” checks authenticated assistant readiness and, only when ready,
posts `/api/assistant/messages` with `mode: "edit"`, `screen: "Product lab"`
and the approved scope. It does not execute on selection or cancel. A blocked
or failed request retains the idea for retry; an accepted response clears only
that idea's pending confirmation. A subsequent chat-list failure cannot resubmit
it. Ordinary unsent drafts persist locally; text typed while a prior message is
in flight is preserved when that earlier message succeeds.

Verified in an isolated browser and signed iOS simulator with a test server:
selection required confirmation; unavailable Start and Send displayed the
blocker and made no message request; recovery plus confirmation sent exactly
one edit request per client; web Cancel sent nothing. No real AI task or source
modification was triggered by these tests. Delayed-response browser checks also
verified that closing/reopening preserves the active request guard, newer drafts
survive acceptance, and completion of idea A keeps newly selected idea B pending.
An independent code review verified the corresponding native model lifecycle.
Signed device build passed and the update installed on the connected iPhone.
The initial launch attempt was blocked because the phone was locked.
Native product-idea execution against the actual Windows conversation remains
blocked by its unavailable transport.

Windows owner: pull the reviewed client changes and build/serve the updated
`mobile-app/dist` with your local backend changes preserved. The Mac did not
restart or overwrite your Windows deployment. This checkout still has the older
assistant implementation; preserve the Windows exact-conversation requirement
when integrating backend files from main.
