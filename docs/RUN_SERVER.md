# Run Pulse on Windows or macOS

Use Python **3.11+**, Node.js LTS, and Git. Paper trading only. The same FastAPI
code serves both platforms. Runtime data and credentials are not in Git.
Coordinate with the other agent before restarting a shared server. Never force
push, overwrite another agent's work, or replace Caddy on port 8080.

## Windows PowerShell

```powershell
git clone https://github.com/varunpra97/project-money.git
cd project-money
.\start-pulse-backend.ps1 -Setup
```

This creates the virtual environment, installs Python dependencies, builds the
web app, and starts http://127.0.0.1:8505/pulse/ . Subsequent starts:

```powershell
.\start-pulse-backend.ps1
```

For the intended server behind the existing Caddy configuration:

```powershell
.\start-pulse-backend.ps1 -ListenHost 127.0.0.1 -Port 8504
```

To allow your own iPhone on a trusted LAN, choose the actual server IP below,
configure the Windows firewall for that private network, then:

```powershell
$env:PULSE_ALLOWED_HOSTS = "192.168.1.20"
$env:PULSE_PUBLIC_HOST = "http://192.168.1.20:8505/pulse"
.\start-pulse-backend.ps1 -ListenHost 0.0.0.0 -Port 8505
```

Use HTTPS and authentication before exposing private portfolio/coding services
beyond that trusted network. Do not commit server credentials. If your system
blocks local PowerShell scripts, have the machine owner use the approved script
execution policy; these launchers do not change it.

Optional assistant (sign in on the machine that runs the server):

```powershell
.\setup-pulse-assistant.ps1
```

## macOS Terminal

```bash
git clone https://github.com/varunpra97/project-money.git
cd project-money
bash start-pulse-backend.sh
```

Subsequent starts without rebuilding dependencies:

```bash
PULSE_PORT=8505 bash options-seller/api/run.sh
```

For iPhone testing on your trusted Wi-Fi:

```bash
PULSE_HOST=0.0.0.0 bash start-pulse-backend.sh
bash setup-pulse-assistant.sh
```

The Mac launcher discovers the LAN IP for the assistant pairing link. Update
the Debug address in `ios-app/Pulse/Config.swift` if it changes. Release builds
use the canonical backend in `docs/LIVE_URLS.md`. Native iOS source changes need
an Xcode rebuild/install. Simulator uses localhost.

## State and fresh data

Every client dataset is served or collected by the backend. No client needs
Python, local scanner files or a copy of portfolio JSON. Before moving machines,
copy your private paper portfolio and observed performance history to the new
server through your own secure transfer. A Git clone intentionally cannot
restore private trading data.

For a persistent folder outside the checkout, set this before starting:

```powershell
$env:PULSE_DATA_DIR = "C:\PulseData"
.\start-pulse-backend.ps1
```

```bash
PULSE_DATA_DIR="$HOME/PulseData" bash start-pulse-backend.sh
```

Portfolio, performance snapshots, saved historical scanners, news, market
statistics, generated scans and assistant state use this folder. Absolute paths
are recommended; relative `PULSE_DATA_DIR` values resolve against `options-seller`,
independently of the launch directory. `SCANNER_JSON_PATH` overrides only the
scanner file. Do not commit any contents of a custom data directory.

Keep the server's existing `options-seller/data/paper_portfolio.json` when
updating. A new clone starts with no private portfolio; do not invent one.
For explicitly demo-only Mac testing, `PULSE_SEED_DEMO=1` can seed the sample
book if no portfolio exists. Both platforms run identical backend code.

Stock prices are received via Yahoo WebSocket when available. HTTP fallback
checks quiet symbols every 20 seconds. Recently requested chart histories and
paper-position underlyings refresh in the background, with a 20-second target
and four concurrent provider workers. Clients receive SSE updates immediately.
Source delays/rate limits can exceed that target; age/stale fields tell clients
what actually arrived. Quotes, option Greeks, and recorded paper P&L are
separate—stock ticks do not manufacture new option marks.

Both standalone launchers enable `PULSE_SCAN_COLLECTOR=1`, which runs the shared
Python scanner every five minutes and retains its last file if the provider
returns no usable prices. Set it to `0` when a separate scanner service already
owns collection. The canonical `api/run.sh` keeps the separate-service default.
The API also warms portfolio/statistics, news, Discover and performance data in
background tasks every five minutes; live subscriptions and requested chart
caches keep their faster independent refresh. Arbitrary ticker histories and
saved historical rules are fetched on demand on the server. Past portfolio
snapshots and individual option marks cannot be recreated from stock prices.

To run the collector manually, from `options-seller` using the server's Python:

```bash
python -m api.collect_scan --symbols AAPL,MSFT,SPY
```

The same command works in PowerShell. Use the venv Python path shown below.

## Verify the data on the actual server

After startup, run this in `options-seller` on either platform:

```bash
python -m api.check_data --base-url http://127.0.0.1:8505 --symbol AAPL
```

Use `api/.venv-pulse/bin/python` on Mac or `api/.venv-pulse/Scripts/python.exe`
on Windows in place of `python`. This reads all client data endpoints, checks
OHLCV contents across five chart ranges, four performance windows, news links,
scanner prices, ticker statistics and live timestamps, and runs a historical
scan to verify actual input bars (zero matches alone is not success). It does
not place trades, save a scanner configuration, or send an AI chat. The report
contains counts/statuses, not portfolio values. Exit code 2 means something is
missing, stale or degraded; read the individual issues. Closed markets may
produce stale live prices, and a new book will lack week/month/quarter baselines.
`GET /api/data/status` provides quick cached collector status and checks whether
the server's portfolio file exists. HTTP health alone is not data readiness.

Assistant sign-in is a separate machine-specific prerequisite. Run the setup
script there, open Assistant on that server's localhost, and send a test message
before pairing a phone. Repository source is read on the server; native source
edits still require a Mac with Xcode to build iOS.

## Verification commands for agents

Windows:

```powershell
$env:PYTHONPATH = "options-seller/src;options-seller"
$Python = ".\options-seller\api\.venv-pulse\Scripts\python.exe"
& $Python -m unittest discover -s options-seller/tests/unit -p "test_p*.py" -v
& $Python -m unittest discover -s options-seller/tests/integration -p "test_live_latency.py" -v
npm --prefix mobile-app test
npm --prefix mobile-app run build
Invoke-RestMethod http://127.0.0.1:8505/api/health
Invoke-RestMethod "http://127.0.0.1:8505/api/live?symbols=AAPL"
```

Mac:

```bash
cd options-seller
PYTHONPATH=src:. api/.venv-pulse/bin/python -m unittest discover -s tests/unit -p 'test_p*.py' -v
PYTHONPATH=src:. api/.venv-pulse/bin/python -m unittest discover -s tests/integration -p test_live_latency.py -v
cd ..
npm --prefix mobile-app test
npm --prefix mobile-app run build
curl -fsS http://127.0.0.1:8505/api/health
curl -N 'http://127.0.0.1:8505/api/live/events?symbols=AAPL'
```

The latency test uses real localhost TCP/HTTP and deterministic injected ticks;
it excludes provider, WAN and phone rendering latency. Run it on Windows and
record p50/p95 before calling that deployment verified. Check the actual public
SSE path too: Caddy uses `flush_interval -1`; other proxies must not buffer it.

## App features in this update

The Scanners tab configures daily, weekly or monthly historical technical scans
for up to 20 tickers. Save a configuration, then run SMA, RSI or prior-high
breakout rules. Signals are historical observations, not simulated trades.

The Positions display selector switches between total gain/loss, today's
gain/loss, return on opening premium, and signed net option equity. Today's
gain/loss remains unavailable until prior-day option marks are recorded; it is
never inferred from stock-price moves. Short option equity is a liability and
excludes collateral and underlying shares. Expirations and leg strikes are
shown when recorded in the paper portfolio.

On the Mac, open the Assistant at `http://localhost:8505/` to find the eight-digit
pairing code. Enter it in the native iPhone assistant. Codes expire after ten
minutes. The web pairing QR is generated locally, without a third-party QR service.

## Shared-agent handoff

Read `docs/BACKEND.md` and `docs/LIVE_URLS.md` before deployment. Fetch and rebase
before pushing, resolve conflicts without deleting newer routes, and run the
contract tests. Required routes include health/risk/scan, portfolio, news,
performance, symbol details, OHLC quotes, live SSE, and paired assistant APIs.
Windows-server credentials belong in local environment/secret storage, not the
repo. Windows and macOS CI validate dependencies, content/collection contracts,
storage paths (including spaces), background cache behavior and TCP delivery.
CI uses controlled provider fixtures. It does not prove that the intended
Windows host has your private data, provider connectivity or assistant sign-in.
