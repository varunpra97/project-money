"""Event risk: upcoming earnings, ex-dividend, and FOMC decision dates.

GET /api/events?symbols=AAPL,MSFT returns per-symbol earnings/ex-dividend
dates (via yfinance) plus a curated list of upcoming FOMC decision dates.
The iOS app shows these beside open positions with plain-language exposure
notes ("Event risk beside every position" product upgrade).

Results are cached 6h in data/events.json with atomic writes. A symbol that
fails to resolve never fails the whole request; the endpoint never 500s.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("pulse.events")

CACHE_SECONDS = 6 * 3600
MAX_SYMBOLS = 25

# Scheduled FOMC decision dates (curated; filtered to future dates on read).
FOMC_DATES = [
    "2026-10-28", "2026-12-09",
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-16",
    "2027-07-28", "2027-09-22", "2027-11-03", "2027-12-15",
]


def _path() -> Path:
    from options_seller.paths import data_dir
    return data_dir() / "events.json"


def _load_cache() -> dict:
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(raw, dict) and time.time() - float(raw.get("as_of_ts", 0)) < CACHE_SECONDS:
            return raw
    except Exception:
        pass
    return {}


def _save_cache(payload: dict) -> None:
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(p)
    except Exception:
        log.warning("events cache write failed", exc_info=True)


def _iso(d: Any) -> Optional[str]:
    if d is None:
        return None
    try:
        if hasattr(d, "date"):
            d = d.date()
        s = d.isoformat()[:10]
        return s if len(s) == 10 else None
    except Exception:
        return None


def _symbol_events(symbol: str) -> dict:
    """Best-effort earnings + ex-dividend dates for one symbol."""
    out: dict[str, Any] = {"earnings_date": None, "ex_dividend_date": None}
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        today = date.today().isoformat()
        try:
            ed = t.earnings_dates
            if ed is not None and not ed.empty:
                future = [d for d in ed.index if (_iso(d) or "") >= today]
                if future:
                    out["earnings_date"] = _iso(future[0])
        except Exception:
            pass
        if not out["earnings_date"]:
            try:
                cal = t.calendar
                if isinstance(cal, dict):
                    val = cal.get("Earnings Date")
                    if isinstance(val, (list, tuple)):
                        val = val[0] if val else None
                    if (_iso(val) or "") >= today:
                        out["earnings_date"] = _iso(val)
            except Exception:
                pass
        try:
            info = t.info or {}
            ts = info.get("exDividendDate")
            if ts:
                out["ex_dividend_date"] = datetime.fromtimestamp(
                    int(ts), tz=timezone.utc).date().isoformat()
        except Exception:
            pass
    except Exception:
        log.warning("events lookup failed for %s", symbol, exc_info=True)
    return out


def get_events(symbols: str) -> dict:
    syms = [s.strip().upper() for s in (symbols or "").split(",") if s.strip()][:MAX_SYMBOLS]
    today = date.today().isoformat()
    fomc = [d for d in FOMC_DATES if d >= today]

    cached = _load_cache()
    cached_events = cached.get("events", {}) if cached else {}
    missing = [s for s in syms if s not in cached_events]

    fresh: dict[str, dict] = {}
    if missing:
        try:
            with ThreadPoolExecutor(max_workers=min(8, len(missing))) as ex:
                for sym, ev in zip(missing, ex.map(_symbol_events, missing)):
                    fresh[sym] = ev if isinstance(ev, dict) else {}
        except Exception:
            log.warning("events batch lookup failed", exc_info=True)
    events = dict(cached_events)
    events.update(fresh)
    blank = {"earnings_date": None, "ex_dividend_date": None}
    resp_events = {s: events.get(s, blank) for s in syms}
    _save_cache({"as_of_ts": time.time(), "events": events})
    return {"events": resp_events,
            "fomc_dates": fomc,
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds")}
