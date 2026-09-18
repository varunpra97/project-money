#!/usr/bin/env python3
"""Quick smoke test: fetch tickers, write scan-latest.json, print sample prices."""

from __future__ import annotations

import json
import sys

from scan import SCAN_PATH, write_scan


def main() -> int:
    universe = ["AAPL", "MSFT"]
    print(f"Fetching {universe} …")
    envelope = write_scan(universe)
    print(f"Wrote {SCAN_PATH}")
    print(f"schema={envelope.get('schema')} asOf={envelope.get('asOf')}")

    ok = 0
    for r in envelope.get("results") or []:
        sym = r.get("symbol")
        price = r.get("price")
        chg = r.get("changePct")
        name = r.get("name")
        print(f"  {sym}: name={name!r} price={price} changePct={chg} bias={r.get('trend', {}).get('bias')}")
        if price is not None:
            ok += 1
        # Basic contract checks
        for key in (
            "symbol", "price", "change", "changePct", "previousClose", "open",
            "dayHigh", "dayLow", "volume", "avgVolume", "marketCap", "bid", "ask",
            "sector", "industry", "pe", "eps", "beta", "dividendYield",
            "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "trend", "liquidity",
            "earnings", "options", "markers",
        ):
            if key not in r:
                print(f"FAIL: missing key {key} on {sym}", file=sys.stderr)
                return 1
        if r["options"].get("suggested") is not None:
            # MVP expects null; if present later, OK — just note
            pass

    raw = json.loads(SCAN_PATH.read_text())
    assert raw["schema"] == "stock-data-scanner.scan/v0.1"
    assert raw["source"] == "yahoo_finance"

    if ok < 1:
        print("FAIL: no prices returned (possible rate limit / network)", file=sys.stderr)
        return 2
    print(f"OK — {ok}/{len(universe)} tickers returned a price")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
