"""Run on Windows/Mac/Linux against a running Pulse server: python -m api.check_data."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import re
import time
from urllib.request import Request, urlopen
from .data_contract import assess, probes


def fetch(base, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = Request(base.rstrip("/")+path, data=data,
                      headers={"Content-Type":"application/json", "X-Pulse-Scanner":"1"})
    with urlopen(request, timeout=45) as response:
        return json.load(response)


def check(base, symbol, history=True):
    def probe(item):
        name, path = item
        try:
            payload = fetch(base, path)
            # Initial subscription returns immediately; let the server obtain the first tick/bar.
            deadline = time.monotonic()+25
            while name == "live" and any(q.get("state") == "connecting" for q in payload.get("quotes", [])) and time.monotonic() < deadline:
                time.sleep(.5)
                payload = fetch(base, path)
            return assess(name, payload)
        except Exception as error:
            return assess(name, {"error":str(error)})
    with ThreadPoolExecutor(max_workers=4) as pool:
        checks = list(pool.map(probe, probes(symbol).items()))
    if history:
        try:
            today = datetime.now(timezone.utc).date()
            job = fetch(base, "/api/history/run", {"name":"Server readiness probe", "symbols":[symbol],
                        "start":(today-timedelta(days=30)).isoformat(), "end":today.isoformat(),
                        "interval":"1d", "rule":"sma20_cross_up"})
            deadline = time.monotonic()+60
            while job["state"] == "running" and time.monotonic() < deadline:
                time.sleep(.5)
                job = fetch(base, "/api/history/jobs/"+job["id"])
            checks.append(assess("history", job.get("result") or {"error":job.get("error") or "History probe timed out"}))
        except Exception as error:
            checks.append(assess("history", {"error":str(error)}))
    try:
        server = fetch(base, "/api/data/status")
    except Exception as error:
        server = {"portfolio_store":"unknown", "error":str(error)}
    return {"ready":all(c["state"] == "ready" for c in checks) and server.get("portfolio_store") == "ready",
            "checks":checks, "server":server,
            "scope":"Server HTTP payloads and historical collection; excludes signed-in assistant, device rendering and exchange latency."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8505")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--skip-history", action="store_true")
    args = parser.parse_args()
    symbol = args.symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=-]{0,19}", symbol):
        parser.error("Invalid ticker symbol")
    report = check(args.base_url, symbol, not args.skip_history)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ready"] else 2)


if __name__ == "__main__":
    main()
