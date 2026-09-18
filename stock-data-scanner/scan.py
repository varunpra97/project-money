"""Stock Data Scanner — Yahoo Finance fetch + scan-latest.json export."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

SCHEMA_ID = "stock-data-scanner.scan/v0.1"
# Priority set from Celebrity Portfolio Scanner (2026-09-18 PT), then liquid anchors.
DEFAULT_UNIVERSE = [
    "SPCX", "AMZN", "GOOGL", "NFLX", "META", "CBRS", "HD", "INTC", "UBER",
    "VST", "TEM", "BE",
    # Honorable mentions (capacity)
    "FDXF", "V", "MA", "SPGI", "AVGO",
    # Liquid market anchors
    "SPY", "QQQ",
]
PROJECT_DIR = Path(__file__).resolve().parent
SCAN_PATH = PROJECT_DIR / "scan-latest.json"

# Fields we always track for markers.available / markers.missing
MARKER_KEYS = [
    "symbol", "name", "price", "change", "changePct", "previousClose", "open",
    "dayHigh", "dayLow", "volume", "avgVolume", "marketCap", "bid", "ask",
    "sector", "industry", "pe", "eps", "beta", "dividendYield",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
]


def _n(v: Any) -> Any:
    """Normalize a value: NaN/None/empty -> None; never invent numbers."""
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    # yfinance sometimes returns numpy types
    try:
        import math
        if isinstance(v, (int, float)):
            if math.isnan(float(v)) or math.isinf(float(v)):
                return None
            return float(v) if not isinstance(v, bool) and (
                isinstance(v, float) or (isinstance(v, int) and not isinstance(v, bool))
            ) else v
    except Exception:
        pass
    if isinstance(v, str) and not v.strip():
        return None
    return v


def _num(v: Any) -> float | None:
    x = _n(v)
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _str(v: Any) -> str | None:
    x = _n(v)
    if x is None:
        return None
    return str(x)


def _safe_info(ticker: yf.Ticker) -> dict:
    try:
        info = ticker.info or {}
        return info if isinstance(info, dict) else {}
    except Exception:
        return {}


def _sma(closes: pd.Series, window: int) -> float | None:
    if closes is None or len(closes) < window:
        return None
    val = closes.tail(window).mean()
    return _num(val)


def _trend(price: float | None, hist: pd.DataFrame | None) -> dict:
    sma20 = sma50 = sma200 = None
    if hist is not None and not hist.empty and "Close" in hist.columns:
        closes = hist["Close"].dropna()
        sma20 = _sma(closes, 20)
        sma50 = _sma(closes, 50)
        sma200 = _sma(closes, 200)

    price_vs = None
    bias = "neutral"
    if price is not None and sma50 is not None and sma50 != 0:
        price_vs = ((price - sma50) / sma50) * 100.0
        if price > sma50 * 1.005:
            bias = "bullish"
        elif price < sma50 * 0.995:
            bias = "bearish"
        else:
            bias = "neutral"

    return {
        "bias": bias,
        "sma20": sma20,
        "sma50": sma50,
        "sma200": sma200,
        "priceVsSma50Pct": _num(price_vs),
    }


def _liquidity(volume: float | None, avg_volume: float | None) -> dict:
    ratio = None
    if volume is not None and avg_volume is not None and avg_volume != 0:
        ratio = volume / avg_volume
    return {
        "volume": volume,
        "avgVolume": avg_volume,
        "volumeRatio": _num(ratio),
    }


def _earnings(ticker: yf.Ticker) -> dict:
    next_date = None
    days_to = None
    try:
        cal = ticker.calendar
        # calendar can be dict or DataFrame depending on yfinance version
        raw = None
        if isinstance(cal, dict):
            raw = cal.get("Earnings Date") or cal.get("earningsDate")
            if isinstance(raw, (list, tuple)) and raw:
                raw = raw[0]
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            if "Earnings Date" in cal.index:
                raw = cal.loc["Earnings Date"].iloc[0] if len(cal.columns) else None
            elif "Earnings Date" in cal.columns:
                raw = cal["Earnings Date"].iloc[0]

        if raw is not None:
            ts = pd.Timestamp(raw)
            if pd.notna(ts):
                # normalize to date (UTC-ish)
                if ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")
                else:
                    ts = ts.tz_convert("UTC")
                next_date = ts.date().isoformat()
                now = datetime.now(timezone.utc).date()
                days_to = (ts.date() - now).days
    except Exception:
        pass

    return {"nextDate": next_date, "daysToEarnings": days_to}


def _options_placeholder() -> dict:
    """Options block — all null in MVP.

    Future `suggested` legs must each include: strike, dte, delta, premium,
    bid, ask (or mid), and openInterest. See SCHEMA.md.
    """
    return {
        "iv": None,
        "ivRank": None,
        "ivPercentile": None,
        "impliedMovePct": None,
        "suggested": None,  # list of legs; see SCHEMA.md for leg shape
    }


def _markers(result: dict) -> dict:
    available: list[str] = []
    missing: list[str] = []
    for k in MARKER_KEYS:
        if result.get(k) is None:
            missing.append(k)
        else:
            available.append(k)
    return {"available": available, "missing": missing}


def _safe_fast_info(ticker: yf.Ticker) -> dict:
    """Best-effort fast_info as a plain dict (survives crumb/401 on quoteSummary)."""
    out: dict = {}
    try:
        fi = ticker.fast_info
    except Exception:
        return out
    keys = [
        "last_price", "previous_close", "open", "day_high", "day_low",
        "last_volume", "market_cap", "year_high", "year_low",
        "three_month_average_volume", "ten_day_average_volume",
        "currency", "exchange",
    ]
    for k in keys:
        try:
            out[k] = fi[k]
        except Exception:
            out[k] = None
    return out


def fetch_scan_result(symbol: str) -> dict:
    """Fetch one ticker and build a ScanResult dict.

    Prefer fast_info + history (reliable); fall back to info for fundamentals
    when Yahoo quoteSummary/crumb cooperates.
    """
    symbol = symbol.upper().strip()
    t = yf.Ticker(symbol)
    info = _safe_info(t)
    fast = _safe_fast_info(t)

    # History for SMAs (1y daily is enough for SMA200) and price fallback
    hist = None
    try:
        hist = t.history(period="1y", auto_adjust=True)
        if hist is not None and hist.empty:
            hist = None
    except Exception:
        hist = None

    price = _num(
        fast.get("last_price")
        or info.get("currentPrice")
        or info.get("regularMarketPrice")
    )
    if price is None and hist is not None and not hist.empty:
        price = _num(hist["Close"].iloc[-1])

    prev_close = _num(
        fast.get("previous_close")
        or info.get("previousClose")
        or info.get("regularMarketPreviousClose")
    )
    # If fast_info previous_close ~= last_price (after-hours / same print), use prior bar
    if (
        hist is not None
        and not hist.empty
        and len(hist) >= 2
        and prev_close is not None
        and price is not None
        and abs(prev_close - price) < max(0.02, abs(price) * 1e-5)
    ):
        prev_close = _num(hist["Close"].iloc[-2])

    change = None
    change_pct = None
    if price is not None and prev_close is not None and abs(prev_close) > 1e-12:
        change = price - prev_close
        change_pct = (change / prev_close) * 100.0

    volume = _num(
        fast.get("last_volume")
        or info.get("volume")
        or info.get("regularMarketVolume")
    )
    avg_volume = _num(
        fast.get("three_month_average_volume")
        or fast.get("ten_day_average_volume")
        or info.get("averageVolume")
        or info.get("averageDailyVolume10Day")
        or info.get("averageVolume10days")
    )
    market_cap = _num(fast.get("market_cap") or info.get("marketCap"))
    div_yield = _num(info.get("dividendYield"))

    result = {
        "symbol": symbol,
        "name": _str(info.get("shortName") or info.get("longName")),
        "price": price,
        "change": _num(change),
        "changePct": _num(change_pct),
        "previousClose": prev_close,
        "open": _num(fast.get("open") or info.get("open") or info.get("regularMarketOpen")),
        "dayHigh": _num(fast.get("day_high") or info.get("dayHigh") or info.get("regularMarketDayHigh")),
        "dayLow": _num(fast.get("day_low") or info.get("dayLow") or info.get("regularMarketDayLow")),
        "volume": volume,
        "avgVolume": avg_volume,
        "marketCap": market_cap,
        "bid": _num(info.get("bid")),
        "ask": _num(info.get("ask")),
        "sector": _str(info.get("sector")),
        "industry": _str(info.get("industry")),
        "pe": _num(info.get("trailingPE") or info.get("forwardPE")),
        "eps": _num(info.get("trailingEps") or info.get("epsTrailingTwelveMonths")),
        "beta": _num(info.get("beta")),
        "dividendYield": div_yield,
        "fiftyTwoWeekHigh": _num(fast.get("year_high") or info.get("fiftyTwoWeekHigh")),
        "fiftyTwoWeekLow": _num(fast.get("year_low") or info.get("fiftyTwoWeekLow")),
        "trend": _trend(price, hist),
        "liquidity": _liquidity(volume, avg_volume),
        "earnings": _earnings(t),
        "options": _options_placeholder(),
    }
    result["markers"] = _markers(result)
    return result


def _error_stub(symbol: str, exc: Exception | str) -> dict:
    """Minimal ScanResult so consumers still see the symbol after a fetch failure."""
    stub = {
        "symbol": symbol.upper(),
        "name": None,
        "price": None,
        "change": None,
        "changePct": None,
        "previousClose": None,
        "open": None,
        "dayHigh": None,
        "dayLow": None,
        "volume": None,
        "avgVolume": None,
        "marketCap": None,
        "bid": None,
        "ask": None,
        "sector": None,
        "industry": None,
        "pe": None,
        "eps": None,
        "beta": None,
        "dividendYield": None,
        "fiftyTwoWeekHigh": None,
        "fiftyTwoWeekLow": None,
        "trend": {
            "bias": "neutral",
            "sma20": None,
            "sma50": None,
            "sma200": None,
            "priceVsSma50Pct": None,
        },
        "liquidity": {"volume": None, "avgVolume": None, "volumeRatio": None},
        "earnings": {"nextDate": None, "daysToEarnings": None},
        "options": _options_placeholder(),
        "error": str(exc),
    }
    stub["markers"] = _markers(stub)
    return stub


def build_scan(universe: list[str] | None = None, max_workers: int = 8) -> dict:
    """Fetch all tickers. Per-ticker Yahoo calls run in a thread pool (I/O bound)."""
    symbols = [s.upper().strip() for s in (universe or DEFAULT_UNIVERSE)]
    results: list[dict | None] = [None] * len(symbols)

    def _one(idx: int, sym: str) -> tuple[int, dict]:
        try:
            return idx, fetch_scan_result(sym)
        except Exception as exc:
            return idx, _error_stub(sym, exc)

    workers = max(1, min(max_workers, len(symbols) or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_one, i, sym) for i, sym in enumerate(symbols)]
        for fut in as_completed(futs):
            idx, row = fut.result()
            results[idx] = row

    return {
        "schema": SCHEMA_ID,
        "asOf": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yahoo_finance",
        "universe": symbols,
        "results": [r for r in results if r is not None],
    }


def write_scan(universe: list[str] | None = None, path: Path | None = None) -> dict:
    """Build scan and atomically write scan-latest.json. Returns the envelope."""
    envelope = build_scan(universe)
    out = path or SCAN_PATH
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    tmp.replace(out)
    return envelope


def get_quote_row(result: dict) -> dict:
    """Flatten a ScanResult for the overview table."""
    return {
        "Symbol": result.get("symbol"),
        "Name": result.get("name"),
        "Price": result.get("price"),
        "Change $": result.get("change"),
        "Change %": result.get("changePct"),
        "Volume": result.get("volume"),
        "Market Cap": result.get("marketCap"),
        "Day High": result.get("dayHigh"),
        "Day Low": result.get("dayLow"),
        "Prev Close": result.get("previousClose"),
    }


def fetch_history(symbol: str, period: str = "1mo") -> pd.DataFrame:
    """Price history for charting. Periods: 1d, 5d, 1mo, 3mo, 1y."""
    interval = "5m" if period == "1d" else ("15m" if period == "5d" else "1d")
    t = yf.Ticker(symbol)
    try:
        df = t.history(period=period, interval=interval, auto_adjust=True)
    except Exception:
        df = pd.DataFrame()
    return df if df is not None else pd.DataFrame()
