"""ThetaHedge daily collector — volatility-based risk/reward rankings.

ThetaHedge (app.thetahedge.io) ranks tickers by option-selling attractiveness:
Wheel Rank, 30-delta put/call yields, IV30 / IV rank. Their ticker-list API is
open (no login required), so we fetch our scanner universe once a day and
merge it into the Pulse scanner.

Endpoint: POST https://app.thetahedge.io/api/stock-table
search_symbol is a SUBSTRING match — always exact-match client-side, never
trust row order.

Output: data_dir()/thetahedge-latest.json ->
  {"asOf": iso, "source": "thetahedge", "total": N,
   "rows": {SYMBOL: {name, price, iv30, iv_rank, hv30, avg_30d_put_yield,
                      avg_30d_call_yield, wheel_rank, wheel_score,
                      wheel_avg_put_yield_3m, wheel_avg_call_yield_3m,
                      days_to_earnings, final_rating, sector,
                      put_30d_contract_id, call_30d_contract_id,
                      put_30d_iv, call_30d_iv}}}

Stdlib only (urllib) — no new dependencies. ~19 requests/day, gentle pacing.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from options_seller.paths import data_dir

log = logging.getLogger(__name__)

API_URL = "https://app.thetahedge.io/api/stock-table"
# NOTE (2026-09-23): the API started returning [] for limit_val >= 75
# (verified: 50 works, 75+ returns 200+[]). Keep PAGE_SIZE at the
# verified-working maximum and adapt down if the API tightens further.
PAGE_SIZE = 50
MIN_PAGE_SIZE = 10
MIN_RANKED_ROWS = 50  # refuse to overwrite good data with a thin response

# Fields we keep per ticker (trimmed from the ~45 the API returns).
KEEP_FIELDS = (
    "name", "price", "iv30", "iv_rank", "hv30",
    "avg_30d_put_yield", "avg_30d_call_yield",
    "wheel_rank", "wheel_score",
    "wheel_avg_put_yield_3m", "wheel_avg_call_yield_3m",
    "days_to_earnings", "final_rating", "sector",
    "put_30d_contract_id", "call_30d_contract_id",
    "put_30d_iv", "call_30d_iv",
)


def _post_page(offset: int, limit: int = PAGE_SIZE,
               condition_strings: list | None = None) -> list[dict]:
    """POST one page with retries (the API occasionally drops connections)."""
    import http.client
    import urllib.error

    body = json.dumps({
        "limit_val": limit,
        "offset_val": offset,
        "sort_column": "wheel_rank",
        "sort_order": "asc",
        "search_symbol": None,
        "condition_strings": condition_strings or [],
        "symbols": None,
        "is_heartbeat": False,
    }).encode()
    last_exc: Exception | None = None
    for attempt in range(6):
        try:
            req = urllib.request.Request(
                API_URL, data=body,
                headers={"Content-Type": "application/json",
                         "Accept": "application/json",
                         "User-Agent": "pulse-scanner/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if not isinstance(data, list):
                raise RuntimeError(
                    f"ThetaHedge returned unexpected shape: {type(data).__name__}")
            return data
        except (http.client.IncompleteRead, http.client.RemoteDisconnected,
                urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_exc = exc
            time.sleep(min(2 ** (attempt + 1), 30))  # 2s, 4s, 8s, 16s, 30s, 30s
    raise RuntimeError(f"ThetaHedge page failed after retries: {last_exc}")


def fetch_all() -> list[dict]:
    """Fetch all ranked tickers (server-side filter keeps it to a few hundred rows).

    The API throttles aggressively: bursts return 200+[] and large page sizes
    (>=75, verified 2026-09-23) return [] outright. We adapt the page size
    downward on empty pages and wait out short throttles before giving up.
    """
    rows: list[dict] = []
    offset = 0
    total = None
    # Prefer the server-side ranked-only filter; fall back to full scan.
    for conditions in (["wheel_rank > 0"], []):
        rows, offset, total = [], 0, None
        page_size = PAGE_SIZE
        try:
            empty_streak = 0
            while True:
                page = _post_page(offset, limit=page_size,
                                  condition_strings=conditions)
                if not page:
                    # Empty page: first try a smaller page (the API silently
                    # empties oversized requests), then wait out throttles.
                    if page_size > MIN_PAGE_SIZE:
                        page_size = max(MIN_PAGE_SIZE, page_size // 2)
                        log.info("ThetaHedge empty page at offset %d; "
                                 "retrying with limit %d", offset, page_size)
                        continue
                    if offset == 0 and empty_streak < 4:
                        empty_streak += 1
                        time.sleep(30)
                        continue
                    break
                empty_streak = 0
                rows.extend(page)
                if total is None:
                    total = page[0].get("total_count")
                offset += len(page)
                if len(page) < page_size:
                    break
                time.sleep(2)  # gentle pacing — the API throttles bursts
            # Filtered query worked and returned ranked rows: done.
            if conditions and any((r.get("wheel_rank") or 0) > 0 for r in rows):
                break
        except RuntimeError:
            if conditions:
                continue  # retry unfiltered
            raise
    return rows


def _slim(row: dict) -> dict:
    out = {"symbol": (row.get("symbol") or "").upper()}
    for f in KEEP_FIELDS:
        out[f] = row.get(f)
    return out


def fetch_symbol(symbol: str) -> dict | None:
    """Fetch one ticker; exact-match client-side with paging.

    search_symbol is a substring match, so the first row is often a different
    (usually unranked) ticker — never trust row order. Page through until the
    exact symbol shows up or the results run out. Page size stays <= 50: the
    API returns [] for limit_val >= 75 (verified 2026-09-23).
    """
    sym = symbol.upper()
    offset = 0
    last_exc: Exception | None = None
    for _ in range(20):  # up to 20 x 50-row pages
        body = json.dumps({
            "limit_val": 50,
            "offset_val": offset,
            "sort_column": "wheel_rank",
            "sort_order": "asc",
            "search_symbol": sym,
            "condition_strings": [],
            "symbols": None,
            "is_heartbeat": False,
        }).encode()
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    API_URL, data=body,
                    headers={"Content-Type": "application/json",
                             "Accept": "application/json",
                             "User-Agent": "pulse-scanner/1.0"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    rows = json.loads(resp.read().decode("utf-8"))
                for r in rows:
                    if (r.get("symbol") or "").upper() == sym:
                        return _slim(r)
                if len(rows) < 50:
                    return None  # ran out of matches: not listed
                offset += 50
                time.sleep(2)  # gentle pacing — the API throttles bursts
                break
            except Exception as exc:  # noqa: BLE001 - retry transient failures
                last_exc = exc
                time.sleep(2 ** (attempt + 1))
        else:
            break
    if last_exc is not None:
        raise RuntimeError(f"ThetaHedge symbol fetch failed for {sym}: {last_exc}")
    return None


def scan_universe() -> list[str]:
    """Tickers the scanner tracks — read from the latest scan envelope."""
    try:
        raw = json.loads((data_dir() / "scan-latest.json").read_text(encoding="utf-8"))
        universe = [s for s in (raw.get("universe") or []) if s]
        if universe:
            return universe
    except Exception:
        pass
    # Fallback mirrors stock-data-scanner/scan.py's universe.
    return ["SPCX", "AMZN", "GOOGL", "NFLX", "META", "CBRS", "HD", "INTC",
            "UBER", "VST", "TEM", "BE", "FDXF", "V", "MA", "SPGI", "AVGO",
            "SPY", "QQQ"]


def fetch_universe() -> list[dict]:
    """Per-symbol pull for the scan universe (~19 gentle requests)."""
    rows: list[dict] = []
    for sym in scan_universe():
        try:
            row = fetch_symbol(sym)
        except RuntimeError:
            row = None
        if row:
            rows.append(row)
        time.sleep(2)  # gentle pacing — the API throttles bursts
    return rows


def target_path() -> Path:
    return data_dir() / "thetahedge-latest.json"


def collect() -> dict:
    """Fetch ThetaHedge rankings and atomically write thetahedge-latest.json.

    Primary: full paginated pull (throttle-aware, adapts page size down).
    Fallback: per-symbol pull for the scan universe with client-side exact
    matching, so the scanner merge still gets fresh data when the full pull
    comes back thin.
    """
    ranked: list[dict] = []
    try:
        raw = fetch_all()
        slimmed = [_slim(r) for r in raw if r.get("symbol")]
        ranked = [r for r in slimmed if (r.get("wheel_rank") or 0) > 0]
    except RuntimeError:
        log.warning("ThetaHedge full pull failed; falling back to universe pull")
    universe_rows: list[dict] = []
    if len(ranked) < MIN_RANKED_ROWS:
        universe_rows = fetch_universe()
    if not ranked and len(universe_rows) < 5:
        raise RuntimeError(
            "ThetaHedge returned no usable rows; previous file retained.")
    merged = {r["symbol"]: r for r in ranked}
    merged.update({r["symbol"]: r for r in universe_rows})

    def _rank_key(r: dict) -> tuple[int, int]:
        wr = r.get("wheel_rank") or 0
        return (0, wr) if wr > 0 else (1, 0)  # ranked first, best rank first

    rows = sorted(merged.values(), key=_rank_key)
    envelope = {
        "asOf": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "thetahedge",
        "total": len(rows),
        "rows": {r["symbol"]: r for r in rows},
    }
    target = target_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(envelope), encoding="utf-8")
    tmp.replace(target)
    return envelope


def load() -> dict | None:
    """Read the latest saved ThetaHedge envelope, or None if missing/invalid."""
    path = target_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("rows"), dict) else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()
    env = collect()
    print(f"Collected {env['total']} ThetaHedge rows at {env['asOf']}")


if __name__ == "__main__":
    main()
