"""Breach scanner: S&P 500 stocks (excluding the 19-ticker watchlist) that
breached a technical level in the past few trading days.

Levels detected (direction shown for each):
  - sma50_cross: daily close crossed above/below the 50-day SMA
  - range_break: daily close broke above the trailing 20-day high or below
    the trailing 20-day low

Writes breaches-latest.json atomically. A thin/empty pull never clobbers a
good file — the previous snapshot is retained instead.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("pulse.breaches")

WINDOW_DAYS = 5          # "past few days" — look back this many trading days
SMA_WINDOW = 50
RANGE_WINDOW = 20
BATCH_SIZE = 100
MIN_BARS = 60            # need enough history for SMA50 + range windows
SP500_CACHE_DAYS = 7

WATCHLIST_19 = {
    "SPCX", "AMZN", "GOOGL", "NFLX", "META", "CBRS", "HD", "INTC", "UBER",
    "VST", "TEM", "BE", "FDXF", "V", "MA", "SPGI", "AVGO", "SPY", "QQQ",
}


def target_path() -> Path:
    from options_seller.paths import data_dir
    return data_dir() / "breaches-latest.json"


def universe_cache_path() -> Path:
    from options_seller.paths import data_dir
    return data_dir() / "sp500-universe.json"


def _bundled_universe() -> list[dict]:
    """Last-resort S&P 500 list shipped with the code, used when both the
    Wikipedia fetch and the disk cache are unavailable (e.g. datacenter IPs
    blocked by Wikipedia)."""
    try:
        data = json.loads(
            Path(__file__).with_name("sp500_fallback.json").read_text(
                encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def sp500_universe() -> list[dict]:
    """S&P 500 (symbol, name), cached for a week, watchlist-19 excluded.

    Wikipedia is the source of truth; the disk cache keeps boots working when
    the fetch fails; a bundled list in the repo is the last resort.
    """
    cache = universe_cache_path()
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            age_days = (time.time() - cache.stat().st_mtime) / 86400
            if isinstance(data, list) and data and age_days < SP500_CACHE_DAYS:
                return [r for r in data if r.get("symbol") not in WATCHLIST_19]
        except Exception:
            pass
    rows: list[dict] = []
    try:
        import io
        import pandas as pd
        import urllib.request
        req = urllib.request.Request(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers={"User-Agent": "Mozilla/5.0 (compatible; PulseScanner/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", errors="replace")
        tables = pd.read_html(io.StringIO(html))
        df = tables[0]
        for _, r in df.iterrows():
            sym = str(r["Symbol"]).strip().upper().replace(".", "-")
            name = str(r["Security"]).strip()
            if sym and sym != "NAN":
                rows.append({"symbol": sym, "name": name})
    except Exception:
        log.warning("S&P 500 fetch failed; trying cache/bundled list",
                    exc_info=True)
    if not rows:
        # Cache may be stale but better than nothing.
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                rows = data
        except Exception:
            pass
    if not rows:
        rows = _bundled_universe()
    if rows:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(rows), encoding="utf-8")
        except Exception:
            pass
    return [r for r in rows if r.get("symbol") not in WATCHLIST_19]


def fetch_history(symbols: list[str]) -> dict[str, "pd.DataFrame"]:
    """Daily OHLC for each symbol (6 months), batched yf.download calls."""
    import pandas as pd
    import yfinance as yf
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i:i + BATCH_SIZE]
        try:
            data = yf.download(
                batch, period="6mo", interval="1d", group_by="ticker",
                auto_adjust=True, threads=True, progress=False)
        except Exception:
            log.warning("history batch %d failed", i // BATCH_SIZE,
                        exc_info=True)
            continue
        for sym in batch:
            try:
                df = data[sym].dropna(subset=["Close"]) if sym in data else None
                if df is not None and len(df) >= MIN_BARS:
                    out[sym] = df
            except Exception:
                continue
        time.sleep(1)
    return out


def detect_breaches(symbol: str, name: str,
                    df: "pd.DataFrame") -> list[dict]:
    """Return breach rows (0-2) for one symbol over the last WINDOW_DAYS."""
    import pandas as pd
    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    sma = close.rolling(SMA_WINDOW).mean()
    hi20 = high.rolling(RANGE_WINDOW).max().shift(1)  # trailing, excl. today
    lo20 = low.rolling(RANGE_WINDOW).min().shift(1)

    rows: list[dict] = []
    price = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    change_pct = (price / prev_close - 1) * 100 if prev_close else 0.0

    def base(breach_type: str, direction: str, date, level: float,
             level_label: str) -> dict:
        dist = abs(price - level) / level * 100 if level else 0.0
        return {
            "symbol": symbol,
            "name": name,
            "price": round(price, 2),
            "changePct": round(change_pct, 2),
            "breach_type": breach_type,
            "direction": direction,
            "breach_date": pd.Timestamp(date).strftime("%Y-%m-%d"),
            "level": round(float(level), 2),
            "level_label": level_label,
            "distance_pct": round(float(dist), 2),
        }

    n = len(df)
    # Most recent event in the window wins for each breach type.
    cross = None
    for j in range(n - WINDOW_DAYS, n):
        if j < 1 or pd.isna(sma.iloc[j]) or pd.isna(sma.iloc[j - 1]):
            continue
        before = close.iloc[j - 1] - sma.iloc[j - 1]
        after = close.iloc[j] - sma.iloc[j]
        if before == 0 or after == 0:
            continue
        if (before < 0) != (after < 0):
            direction = "bullish" if after > 0 else "bearish"
            cross = base("sma50_cross", direction, df.index[j],
                         sma.iloc[j], "50-day SMA")
    if cross:
        rows.append(cross)

    brk = None
    for j in range(n - WINDOW_DAYS, n):
        if pd.isna(hi20.iloc[j]) or pd.isna(lo20.iloc[j]):
            continue
        c = close.iloc[j]
        if c > hi20.iloc[j]:
            brk = base("range_break", "bullish", df.index[j],
                       hi20.iloc[j], "20-day high")
        elif c < lo20.iloc[j]:
            brk = base("range_break", "bearish", df.index[j],
                       lo20.iloc[j], "20-day low")
    if brk:
        rows.append(brk)
    return rows


def collect() -> dict:
    """Run the breach scan and atomically write breaches-latest.json."""
    universe = sp500_universe()
    if not universe:
        raise RuntimeError("No S&P 500 universe available; previous file retained.")
    symbols = [r["symbol"] for r in universe]
    names = {r["symbol"]: r["name"] for r in universe}
    hist = fetch_history(symbols)

    results: list[dict] = []
    for sym, df in hist.items():
        try:
            results.extend(detect_breaches(sym, names.get(sym, sym), df))
        except Exception:
            log.warning("breach detect failed for %s", sym, exc_info=True)

    # Most recent breach first, then furthest past the level.
    results.sort(key=lambda r: (r["breach_date"], r["distance_pct"]),
                 reverse=True)
    envelope = {
        "asOf": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yahoo_finance",
        "window_days": WINDOW_DAYS,
        "universe_count": len(symbols),
        "scanned_count": len(hist),
        "total": len(results),
        "results": results,
    }
    prev = load()
    if not results and prev and prev.get("results"):
        log.warning("Breach scan found nothing (%d scanned); keeping previous "
                    "file from %s", len(hist), prev.get("asOf"))
        return prev
    target = target_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(envelope), encoding="utf-8")
    tmp.replace(target)
    return envelope


def load() -> dict | None:
    """Read the latest saved breach envelope, or None if missing/invalid."""
    path = target_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("results"), list) else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", help="Comma-separated tickers to scan instead of S&P 500")
    args = parser.parse_args()
    if args.symbols:
        import pandas as pd
        import yfinance as yf
        syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        hist = fetch_history(syms)
        rows = []
        for sym, df in hist.items():
            rows.extend(detect_breaches(sym, sym, df))
        rows.sort(key=lambda r: (r["breach_date"], r["distance_pct"]), reverse=True)
        print(json.dumps(rows, indent=2))
        print(f"{len(rows)} breaches across {len(hist)} tickers")
        return
    env = collect()
    print(f"Collected {env['total']} breaches ({env['scanned_count']}/{env['universe_count']} scanned) at {env['asOf']}")


if __name__ == "__main__":
    main()
