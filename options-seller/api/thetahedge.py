"""ThetaHedge daily collector — volatility-based risk/reward rankings.

ThetaHedge (app.thetahedge.io) ranks tickers by option-selling attractiveness:
Wheel Rank, 30-delta put/call yields, IV30 / IV rank. Their ticker-list API is
open (no login required), so we fetch it once a day and merge it into the
Pulse scanner.

Endpoint: POST https://app.thetahedge.io/api/stock-table
Response: JSON array of row objects; each row carries total_count.

Output: data_dir()/thetahedge-latest.json ->
  {"asOf": iso, "source": "thetahedge", "total": N,
   "rows": {SYMBOL: {name, price, iv30, iv_rank, hv30, avg_30d_put_yield,
                      avg_30d_call_yield, wheel_rank, wheel_score,
                      wheel_avg_put_yield_3m, wheel_avg_call_yield_3m,
                      days_to_earnings, final_rating, sector,
                      put_30d_contract_id, call_30d_contract_id}}}

Stdlib only (urllib) — no new dependencies. ~19 requests/day, gentle pacing.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from options_seller.paths import data_dir

API_URL = "https://app.thetahedge.io/api/stock-table"
PAGE_SIZE = 100
MIN_RANKED_ROWS = 100  # refuse to overwrite good data with a thin response

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
    for attempt in range(4):
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
            time.sleep(2 ** (attempt + 1))  # 2s, 4s, 8s, 16s
    raise RuntimeError(f"ThetaHedge page failed after retries: {last_exc}")


def fetch_all() -> list[dict]:
    """Fetch all ranked tickers (server-side filter keeps it to a few hundred rows)."""
    rows: list[dict] = []
    offset = 0
    total = None
    # Prefer the server-side ranked-only filter; fall back to full scan.
    for conditions in (["wheel_rank > 0"], []):
        rows, offset, total = [], 0, None
        try:
            empty_streak = 0
            while True:
                page = _post_page(offset, condition_strings=conditions)
                if not page:
                    # An empty FIRST page is suspicious (throttle returns 200+[]);
                    # wait it out briefly before accepting it as end-of-data.
                    if offset == 0 and empty_streak < 2:
                        empty_streak += 1
                        time.sleep(30)
                        continue
                    break
                rows.extend(page)
                if total is None:
                    total = page[0].get("total_count")
                offset += len(page)
                if len(page) < PAGE_SIZE:
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


def target_path() -> Path:
    return data_dir() / "thetahedge-latest.json"


def collect() -> dict:
    """Fetch all ThetaHedge rows and atomically write thetahedge-latest.json."""
    raw = fetch_all()
    slimmed = [_slim(r) for r in raw if r.get("symbol")]
    ranked = [r for r in slimmed if (r.get("wheel_rank") or 0) > 0]
    if len(ranked) < MIN_RANKED_ROWS:
        raise RuntimeError(
            f"ThetaHedge returned only {len(ranked)} ranked rows; previous file retained.")
    ranked.sort(key=lambda r: r["wheel_rank"])
    envelope = {
        "asOf": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "thetahedge",
        "total": len(ranked),
        "rows": {r["symbol"]: r for r in ranked},
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
