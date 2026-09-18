"""Live market signals for the tracker universe: upcoming earnings + recent volatility.

Universe defaults to the celebrity tracker symbols
(:func:`celebrity_priority.symbols`), so the dashboard's tracker panel can show,
next to the ranked 13F / disclosure moves:

* **Earnings radar** — stocks reporting now or within the next 14 days
  (plus anything that reported in the last 7 days).
* **Volatility watch** — stocks with outsized recent moves: big single-day
  jumps, high 20-day realized volatility, or a wide ATR(14).

Data comes from Yahoo Finance via ``yfinance`` (free, no API key) and is cached
to ``market_signals_cache.json`` next to this file, so the dashboard never
blocks on the network when a fresh-enough snapshot exists.

This module performs no trading and emits no signals to buy/sell — it is
context for an educational paper-trading dashboard.
"""

from __future__ import annotations

import json
import math
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

try:  # yfinance is optional at import time; network features degrade gracefully.
    import yfinance as yf
except Exception:  # pragma: no cover - import guard
    yf = None  # type: ignore[assignment]

HERE = Path(__file__).resolve().parent
CACHE_PATH = HERE / "market_signals_cache.json"

# --- thresholds ---------------------------------------------------------------
EARNINGS_UPCOMING_DAYS = 14   # "nearby" earnings: reporting within N days
EARNINGS_RECENT_DAYS = 7      # "current" earnings: reported within last N days
BIG_DAY_PCT = 5.0             # single-day |move| in last 10 sessions -> volatile
LAST_DAY_PCT = 4.0            # |move| of the most recent session -> volatile
REALIZED_VOL_PCT = 60.0       # 20-day realized vol (annualized %) -> volatile
ATR_PCT = 4.0                 # ATR(14) as % of price -> volatile
CACHE_TTL_HOURS = 6.0


# --- pure computation (unit-tested, no network) --------------------------------

def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten yfinance MultiIndex columns to plain Title-case names."""
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [str(c[0]).title() for c in out.columns]
    else:
        out.columns = [str(c).title() for c in out.columns]
    # yfinance 0.2.31+: 'Adj Close' may appear instead of adjusted 'Close'.
    if "Close" not in out.columns and "Adj Close" in out.columns:
        out["Close"] = out["Adj Close"]
    return out


def compute_volatility(df: pd.DataFrame) -> dict:
    """Compute recent-volatility metrics from daily OHLC bars (oldest -> newest).

    Returns a dict with last price, 1-day / 5-day % changes, 20-day realized
    volatility (annualized %), max absolute 1-day move over the last 10
    sessions, ATR(14) as % of last price, plus a ``volatile`` flag and the
    human-readable ``reasons`` that tripped it. Empty dict when there are too
    few bars (< 6).
    """
    df = _norm_cols(df).sort_index()
    if "Close" not in df.columns:
        return {}
    df = df.dropna(subset=["Close"])
    if len(df) < 6:
        return {}
    close = df["Close"].astype(float)
    last = float(close.iloc[-1])
    if last <= 0:
        return {}

    chg_1d = (last / float(close.iloc[-2]) - 1.0) * 100.0
    chg_5d = (last / float(close.iloc[-6]) - 1.0) * 100.0

    logret = (close / close.shift(1)).apply(
        lambda x: math.log(x) if x > 0 else float("nan")
    ).dropna()
    vol_20d = float(logret.tail(20).std(ddof=1) * math.sqrt(252) * 100.0) \
        if len(logret) >= 20 else float("nan")

    day_pct = (close / close.shift(1) - 1.0) * 100.0
    max_1d_10d = float(day_pct.tail(10).abs().max())

    atr_pct = float("nan")
    if {"High", "Low"}.issubset(df.columns) and len(df) >= 15:
        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        prev_close = close.shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr = float(tr.tail(14).mean())
        atr_pct = atr / last * 100.0

    reasons: list[str] = []
    if max_1d_10d >= BIG_DAY_PCT:
        reasons.append(f"≥{BIG_DAY_PCT:.0f}% single-day move in last 10 sessions")
    if abs(chg_1d) >= LAST_DAY_PCT:
        reasons.append(f"±{LAST_DAY_PCT:.0f}% move in the last session")
    if not math.isnan(vol_20d) and vol_20d >= REALIZED_VOL_PCT:
        reasons.append(f"20d realized vol ≥{REALIZED_VOL_PCT:.0f}% (ann.)")
    if not math.isnan(atr_pct) and atr_pct >= ATR_PCT:
        reasons.append(f"ATR(14) ≥{ATR_PCT:.0f}% of price")

    return {
        "last": round(last, 2),
        "chg_1d_pct": round(chg_1d, 2),
        "chg_5d_pct": round(chg_5d, 2),
        "vol_20d_ann_pct": round(vol_20d, 1) if not math.isnan(vol_20d) else None,
        "max_1d_move_10d_pct": round(max_1d_10d, 2),
        "atr14_pct": round(atr_pct, 2) if not math.isnan(atr_pct) else None,
        "volatile": bool(reasons),
        "reasons": reasons,
    }


def classify_earnings(dates: Iterable[date], today: date | None = None) -> dict:
    """Classify a list of earnings dates relative to ``today``.

    Returns ``{"upcoming": <date|None>, "days_to": int|None,
    "last_reported": <date|None>, "days_since": int|None,
    "nearby": bool}`` where ``nearby`` is True when earnings are within
    ``EARNINGS_UPCOMING_DAYS`` ahead or were reported within
    ``EARNINGS_RECENT_DAYS`` behind.
    """
    today = today or date.today()
    clean = sorted({d for d in dates if d is not None})
    upcoming = next((d for d in clean if d >= today), None)
    last_reported = next((d for d in reversed(clean) if d < today), None)
    days_to = (upcoming - today).days if upcoming else None
    days_since = (today - last_reported).days if last_reported else None
    nearby = (
        (days_to is not None and days_to <= EARNINGS_UPCOMING_DAYS)
        or (days_since is not None and days_since <= EARNINGS_RECENT_DAYS)
    )
    return {
        "upcoming": upcoming.isoformat() if upcoming else None,
        "days_to": days_to,
        "last_reported": last_reported.isoformat() if last_reported else None,
        "days_since": days_since,
        "nearby": bool(nearby),
    }


# --- network fetch ------------------------------------------------------------

def _default_symbols() -> list[str]:
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "celebrity_priority_sig", HERE / "celebrity_priority.py"
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return [str(s).upper() for s in mod.symbols()]
    except Exception:
        pass
    return []


def _download_bars(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Batch-download 6 months of daily bars; returns {symbol: df}."""
    if yf is None or not symbols:
        return {}
    try:
        raw = yf.download(
            " ".join(symbols),
            period="6mo",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception:
        return {}
    if raw is None or len(raw) == 0:
        return {}
    out: dict[str, pd.DataFrame] = {}
    if isinstance(raw.columns, pd.MultiIndex):
        tickers = {str(c[1]).upper() for c in raw.columns}
        for sym in symbols:
            if sym in tickers:
                try:
                    out[sym] = raw.xs(sym, axis=1, level=1)
                except Exception:
                    continue
    else:  # single ticker -> flat columns
        out[symbols[0]] = raw
    return out


def _earnings_dates(symbol: str, today: date) -> list[date]:
    """Upcoming + recent earnings dates for one symbol (best effort)."""
    if yf is None:
        return []
    try:
        t = yf.Ticker(symbol)
        ed = t.get_earnings_dates(limit=12)
        if ed is not None and len(ed):
            idx = pd.DatetimeIndex(pd.to_datetime(ed.index, errors="coerce")).dropna()
            return sorted({ts.date() for ts in idx})
    except Exception:
        pass
    # Fallback: the single next date from the quote calendar.
    try:
        cal = yf.Ticker(symbol).calendar
        if isinstance(cal, dict):
            val = cal.get("Earnings Date")
            vals = val if isinstance(val, (list, tuple)) else [val]
            out = []
            for v in vals:
                try:
                    out.append(pd.to_datetime(v).date())
                except Exception:
                    continue
            return sorted(set(out))
    except Exception:
        pass
    return []


def fetch_market_signals(symbols: list[str] | None = None) -> dict:
    """Fetch earnings + volatility snapshot for ``symbols``.

    Returns ``{"as_of": iso, "symbols": {sym: {...}}, "errors": {sym: msg}}``.
    Never raises for per-symbol failures; they land in ``errors``.
    """
    symbols = [str(s).upper() for s in (symbols or _default_symbols()) if str(s).strip()]
    today = date.today()
    as_of = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload: dict[str, dict] = {}
    errors: dict[str, str] = {}

    bars = _download_bars(symbols)

    with ThreadPoolExecutor(max_workers=8) as pool:
        fut = {pool.submit(_earnings_dates, s, today): s for s in symbols}
        earnings: dict[str, list[date]] = {}
        for f in as_completed(fut):
            s = fut[f]
            try:
                earnings[s] = f.result()
            except Exception as exc:  # pragma: no cover - defensive
                earnings[s] = []
                errors[s] = f"earnings: {exc}"

    for s in symbols:
        try:
            vol = compute_volatility(bars.get(s, pd.DataFrame()))
            if not vol:
                errors.setdefault(s, "no price history")
            payload[s] = {
                "earnings": classify_earnings(earnings.get(s, []), today),
                "volatility": vol,
            }
        except Exception as exc:
            errors[s] = f"compute: {exc}"
            payload[s] = {"earnings": classify_earnings([], today), "volatility": {}}

    return {"as_of": as_of, "symbols": payload, "errors": errors}


# --- cache ---------------------------------------------------------------------

def save_cache(payload: dict, path: Path | None = None) -> Path:
    path = path or CACHE_PATH
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def load_cache(path: Path | None = None, max_age_hours: float = CACHE_TTL_HOURS):
    """Return ``(payload, fresh)``; ``(None, False)`` when missing/stale/broken."""
    path = path or CACHE_PATH
    try:
        raw = json.loads(path.read_text())
        as_of = datetime.fromisoformat(str(raw.get("as_of", "")))
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - as_of
        if age <= timedelta(hours=max_age_hours):
            return raw, True
        return raw, False
    except Exception:
        return None, False


def get_market_signals(
    symbols: list[str] | None = None,
    max_age_hours: float = CACHE_TTL_HOURS,
    refresh: bool = False,
) -> tuple[dict | None, bool]:
    """Cache-first accessor used by the dashboard.

    Returns ``(payload, fresh)``. When the cache is missing/stale (or
    ``refresh=True``) it tries a live fetch; on network failure it falls back
    to the stale cache if one exists.
    """
    if not refresh:
        payload, fresh = load_cache(max_age_hours=max_age_hours)
        if payload is not None and fresh:
            return payload, True
    stale, _ = load_cache(max_age_hours=10_000)
    try:
        payload = fetch_market_signals(symbols)
        # Only overwrite the cache when we actually got data.
        if payload.get("symbols"):
            save_cache(payload)
            return payload, True
    except Exception:
        traceback.print_exc()
    if stale is not None:
        return stale, False
    return None, False


def main() -> None:  # CLI: python market_signals.py [--refresh]
    import argparse

    ap = argparse.ArgumentParser(description="Refresh the market-signals cache.")
    ap.add_argument("--refresh", action="store_true", help="Force a live fetch")
    ap.add_argument("--symbols", nargs="*", default=None)
    args = ap.parse_args()

    payload, fresh = get_market_signals(args.symbols, refresh=args.refresh)
    if payload is None:
        print("No market data available (network unreachable and no cache).")
        raise SystemExit(1)
    n = len(payload.get("symbols", {}))
    earn = sum(
        1 for v in payload["symbols"].values() if v.get("earnings", {}).get("nearby")
    )
    vol = sum(
        1 for v in payload["symbols"].values() if v.get("volatility", {}).get("volatile")
    )
    print(
        f"as_of={payload.get('as_of')} fresh={fresh} symbols={n} "
        f"nearby_earnings={earn} volatile={vol}"
    )
    if payload.get("errors"):
        print("errors:", json.dumps(payload["errors"], indent=2)[:800])


if __name__ == "__main__":
    main()
