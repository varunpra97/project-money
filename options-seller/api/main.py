"""FastAPI backend for the mobile trading-insights app.

EDUCATIONAL / PAPER TRADING ONLY — this API never places live orders. It reads
the same paper-trading store and scan data as the Streamlit dashboard
(dashboard/app.py) and exposes it as low-latency JSON for a mobile frontend.

Aggressive in-memory TTL caching keeps cached responses well under 50ms.
Yahoo Finance is never hammered: market_signals.py keeps its own 6h file
cache, and /api/quote caches per range.
"""

from __future__ import annotations

import functools
import importlib.util
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parents[1]  # options-seller/
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from options_seller.config import load_defaults
from options_seller.models.scanner import PortfolioContext
from options_seller.portfolio.api import (
    days_held,
    load_executor,
    pct_of_max_profit,
    portfolio_greeks_est,
    summary_metrics,
)
from options_seller.portfolio.scanner_feed import build_candidates, load_scan_envelope

# ── Sibling stock-data-scanner modules (same importlib pattern as dashboard) ──
_SCANNER = ROOT.parent / "stock-data-scanner"


def _load_module(name: str, path: Path) -> Optional[Any]:
    try:
        if not path.exists():
            return None
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
    except Exception:
        return None


_celeb = _load_module("celebrity_priority_api", _SCANNER / "celebrity_priority.py")
_signals = _load_module("market_signals_api", _SCANNER / "market_signals.py")

# ── In-memory TTL cache ──────────────────────────────────────────────────────
_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def cached(ttl: int, key: str, fn: Callable[[], Any]) -> Any:
    """Return cached value if fresh, else compute, store and return it."""
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]
    val = fn()
    # Never cache error payloads — transient failures must not stick.
    if isinstance(val, dict) and "error" in val:
        return val
    with _cache_lock:
        _cache[key] = (time.monotonic() + ttl, val)
    return val


def _api(fn):
    """Never 500 on data problems: return structured JSON with an error field."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - deliberate graceful degradation
            return JSONResponse(
                {"error": f"{type(e).__name__}: {e}"}, status_code=200
            )

    return wrapper


# ── Small helpers ────────────────────────────────────────────────────────────
_STRAT_DISPLAY = {
    "cash_secured_put": "Cash-Secured Put",
    "bull_put_spread": "Bull Put Spread",
    "bear_call_spread": "Bear Call Spread",
    "bull_call_spread": "Bull Call Spread",
    "iron_condor": "Iron Condor",
    "iron_butterfly": "Iron Butterfly",
    "covered_call": "Covered Call",
    "jade_lizard": "Jade Lizard",
    "strangle": "Strangle",
    "straddle": "Straddle",
}


def _strat_name(s: Any) -> str:
    if not s:
        return "—"
    key = str(s)
    return _STRAT_DISPLAY.get(key, key.replace("_", " ").title())


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _risk_label(p: dict[str, Any]) -> str:
    """Simple risk tag from max loss vs credit collected (documented heuristic)."""
    credit = float(p.get("credit") or 0)
    max_loss = float(p.get("max_loss") or 0)
    if max_loss <= 0:
        return "none"
    if credit <= 0:
        return "high"
    ratio = max_loss / credit
    if ratio < 3:
        return "low"
    if ratio < 10:
        return "moderate"
    return "high"


def _contract_qty(legs: list[dict]) -> int:
    try:
        return max(int(l.get("quantity") or 1) for l in legs) if legs else 1
    except Exception:
        return 1


def _celeb_universe() -> list[dict[str, Any]]:
    if _celeb is None:
        return []
    return list(getattr(_celeb, "PRIORITY_ROWS", []) or [])


def _celeb_symbols() -> list[str]:
    return [str(r.get("symbol") or "").upper() for r in _celeb_universe()]


# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="Options Seller Mobile API", version="1.0.0")


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/portfolio/summary")
@_api
async def portfolio_summary():
    def _build():
        ex = load_executor()
        m = summary_metrics(ex)
        g = portfolio_greeks_est(ex)
        starting = float(m.get("starting_cash") or 0)
        day_pnl = float(m.get("day_pnl") or 0)
        return {
            "account_value": _num(m.get("net_liquidation")),
            "buying_power": _num(m.get("buying_power")),
            "day_pnl": _num(day_pnl),
            "day_pnl_pct": round(day_pnl / starting * 100, 2) if starting else 0.0,
            "total_pnl": _num(
                float(m.get("realized_pnl") or 0) + float(m.get("unrealized_pnl") or 0)
            ),
            "open_positions": int(m.get("open_positions") or 0),
            "greeks": {
                "delta": _num(g.get("delta")),
                "theta": _num(g.get("theta")),
                "gamma": _num(g.get("gamma")),
                "vega": _num(g.get("vega")),
                "estimated": bool(g.get("estimated")),
            },
            "as_of": _now_iso(),
        }

    return cached(30, "portfolio:summary", _build)


@app.get("/api/portfolio/positions")
@_api
async def portfolio_positions():
    def _build():
        ex = load_executor()
        rows = []
        for p in ex.list_open():
            if p.get("status") != "open":
                continue
            legs = p.get("legs") or []
            rows.append(
                {
                    "id": p.get("id"),
                    "underlying": p.get("underlying"),
                    "strategy": p.get("strategy"),
                    "display_name": _strat_name(p.get("strategy")),
                    "opened_at": p.get("opened_at"),
                    "dte": p.get("dte"),
                    "qty": _contract_qty(legs),
                    "credit": _num(p.get("credit")),
                    "unrealized": _num(p.get("unrealized_pnl")),
                    "pct_of_max_profit": _num(
                        pct_of_max_profit(p.get("unrealized_pnl"), p.get("max_profit"))
                    ),
                    "days_held": _num(days_held(p.get("opened_at"), p.get("closed_at"))),
                    "risk_label": _risk_label(p),
                }
            )
        return {"positions": rows, "as_of": _now_iso()}

    return cached(30, "portfolio:positions", _build)


@app.get("/api/portfolio/activity")
@_api
async def portfolio_activity():
    def _build():
        ex = load_executor()
        fills = ex.list_fills() or []
        rows = []
        for f in fills:
            ftype = str(f.get("type") or "fill")
            sym = f.get("underlying") or "?"
            strat = _strat_name(f.get("strategy"))
            fp = _num(f.get("fill_price"))
            rp = _num(f.get("realized_pnl"))
            if ftype == "close":
                text = f"Closed {strat} on {sym}"
            elif ftype == "risk_trim":
                text = f"Risk trim on {sym}"
            else:
                text = f"Opened {strat} on {sym}"
            rows.append(
                {
                    "ts": f.get("ts"),
                    "kind": ftype,
                    "text": text,
                    "amount": rp if ftype == "close" else fp,
                }
            )
        rows.sort(key=lambda r: str(r.get("ts") or ""), reverse=True)
        return {"activity": rows[:50], "as_of": _now_iso()}

    return cached(30, "portfolio:activity", _build)


@app.get("/api/insights/celebrity")
@_api
async def insights_celebrity():
    def _build():
        rows = _celeb_universe()
        if not rows:
            return {"error": "celebrity tracker module not available"}
        scan_date = getattr(_celeb, "SCAN_DATE", "?")
        live: dict[str, tuple] = {}
        try:
            envelope, _ = load_scan_envelope()
            for r in getattr(envelope, "results", None) or []:
                live[str(r.symbol).upper()] = (r.price, r.changePct)
        except Exception:
            pass
        moves = []
        for r in rows:
            sym = str(r.get("symbol") or "").upper()
            lp, lc = live.get(sym, (None, None))
            moves.append(
                {
                    "rank": r.get("rank"),
                    "symbol": sym,
                    "company": r.get("company"),
                    "investor": r.get("investor"),
                    "what_changed": r.get("what_changed"),
                    "period": r.get("period"),
                    "why": r.get("why"),
                    "heat": r.get("heat"),
                    "live_price": _num(lp),
                    "live_chg_pct": _num(lc),
                }
            )
        return {"scan_date": scan_date, "moves": moves}

    return cached(300, "insights:celebrity", _build)


def _signals_payload(symbols: list[str]) -> tuple[Optional[dict], bool]:
    if _signals is None:
        return None, False
    return _signals.get_market_signals(symbols)


@app.get("/api/insights/earnings")
@_api
async def insights_earnings():
    def _build():
        symbols = _celeb_symbols()
        if _signals is None or not symbols:
            return {"error": "market signals module not available"}
        payload, fresh = _signals_payload(symbols)
        if payload is None:
            return {"error": "earnings data unavailable (Yahoo Finance unreachable)"}
        comp = {s: r.get("company") for s, r in
                ((str(x.get("symbol") or "").upper(), x) for x in _celeb_universe())}
        rows = []
        for sym in symbols:
            e = (payload.get("symbols", {}).get(sym, {}) or {}).get("earnings", {}) or {}
            dt, ds = e.get("days_to"), e.get("days_since")
            if isinstance(dt, int) and dt <= 14:
                when = f"in {dt} day{'s' if dt != 1 else ''}"
                status = "upcoming"
                edate = e.get("upcoming")
            elif isinstance(ds, int) and ds <= 7:
                when = f"{ds} day{'s' if ds != 1 else ''} ago"
                status = "just_reported"
                edate = e.get("last_reported")
            else:
                when, status, edate = "—", "none", e.get("upcoming")
            rows.append(
                {
                    "symbol": sym,
                    "company": comp.get(sym),
                    "earnings_date": edate,
                    "when": when,
                    "status": status,
                    "_sort": dt if isinstance(dt, int) else 99999,
                }
            )
        rows.sort(key=lambda r: (r["_sort"], r["symbol"]))
        for r in rows:
            r.pop("_sort", None)
        return {"as_of": payload.get("as_of"), "fresh": fresh, "rows": rows}

    return cached(600, "insights:earnings", _build)


@app.get("/api/insights/volatility")
@_api
async def insights_volatility():
    def _build():
        symbols = _celeb_symbols()
        if _signals is None or not symbols:
            return {"error": "market signals module not available"}
        payload, fresh = _signals_payload(symbols)
        if payload is None:
            return {"error": "volatility data unavailable (Yahoo Finance unreachable)"}
        comp = {s: r.get("company") for s, r in
                ((str(x.get("symbol") or "").upper(), x) for x in _celeb_universe())}
        rows = []
        for sym in symbols:
            v = (payload.get("symbols", {}).get(sym, {}) or {}).get("volatility", {}) or {}
            rows.append(
                {
                    "symbol": sym,
                    "company": comp.get(sym),
                    "last": _num(v.get("last")),
                    "chg_1d_pct": _num(v.get("chg_1d_pct")),
                    "chg_5d_pct": _num(v.get("chg_5d_pct")),
                    "vol_20d_ann_pct": _num(v.get("vol_20d_ann_pct")),
                    "max_1d_move_10d_pct": _num(v.get("max_1d_move_10d_pct")),
                    "atr14_pct": _num(v.get("atr14_pct")),
                    "volatile": bool(v.get("volatile")),
                    "reasons": list(v.get("reasons") or []),
                    "_sort": -float(v.get("max_1d_move_10d_pct") or 0),
                }
            )
        rows.sort(key=lambda r: (r["_sort"], r["symbol"]))
        for r in rows:
            r.pop("_sort", None)
        return {"as_of": payload.get("as_of"), "fresh": fresh, "rows": rows}

    return cached(600, "insights:volatility", _build)


@app.get("/api/candidates")
@_api
async def candidates():
    def _build():
        envelope, status = load_scan_envelope()
        if envelope is None:
            return {"error": status.get("error") or "scan data unavailable"}
        cfg = load_defaults()
        cands = build_candidates(envelope, portfolio=PortfolioContext(), cfg=cfg)
        good = [c for c in cands if not c.get("skipped")]
        skipped = [c for c in cands if c.get("skipped")]
        picked = (good + skipped)[:20]

        def _row(c: dict[str, Any]) -> dict[str, Any]:
            return {
                "symbol": c.get("symbol"),
                "company": c.get("name"),
                "strategy": c.get("strategy"),
                "display_name": _strat_name(c.get("strategy")),
                "dte": c.get("target_dte"),
                "bias": c.get("bias"),
                "credit_status": (
                    "quoted"
                    if c.get("is_template") is False
                    else ("template" if c.get("is_template") is True else None)
                ),
                "rationale": c.get("reason"),
                "skip_reason": c.get("skip_reason"),
            }

        return {
            "candidates": [_row(c) for c in picked],
            "as_of": status.get("as_of"),
            "source": status.get("source"),
        }

    return cached(60, "candidates", _build)


_QUOTE_RANGES = {
    "1d": ("1d", "5m", 60),
    "5d": ("5d", "15m", 900),
    "1mo": ("1mo", "1d", 900),
    "3mo": ("3mo", "1d", 900),
    "1y": ("1y", "1wk", 900),
}


@app.get("/api/quote/{symbol}")
@_api
async def quote(symbol: str, range: str = Query("1d")):
    rng = str(range or "1d").lower()
    if rng not in _QUOTE_RANGES:
        return {"error": f"range must be one of {sorted(_QUOTE_RANGES)}"}
    period, interval, ttl = _QUOTE_RANGES[rng]
    sym = symbol.strip().upper()

    def _build():
        import yfinance as yf

        df = yf.download(sym, period=period, interval=interval, progress=False,
                         auto_adjust=True)
        if df is None or len(df) == 0:
            return {"error": f"no quote data for {sym}"}
        # yfinance >= 1.x may return MultiIndex columns even for one ticker
        if hasattr(df.columns, "levels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
        closes = df["Close"].dropna() if "Close" in df.columns else df.iloc[:, 0].dropna()
        bars = [
            {"t": int(ts.timestamp()), "c": round(float(c), 2)}
            for ts, c in closes.items()
        ]
        first, last = float(closes.iloc[0]), float(closes.iloc[-1])
        return {
            "symbol": sym,
            "price": round(last, 2),
            "chg_pct": round((last - first) / first * 100, 2) if first else 0.0,
            "bars": bars,
        }

    return cached(ttl, f"quote:{sym}:{rng}", _build)


# ── Frontend SPA (optional) ──────────────────────────────────────────────────
_DIST = ROOT.parent / "mobile-app" / "dist"

if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="spa")
else:

    @app.get("/")
    async def _root():
        return {"note": "frontend not built yet — API only (see /docs)"}


# ── Serve under /pulse too (public tunnel path-routes /pulse/* here) ─────────
class _PulsePrefixStrip:
    """Strip a leading /pulse so the app works both at / and under /pulse."""

    def __init__(self, inner, prefix="/pulse"):
        self.inner = inner
        self.prefix = prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            p = scope.get("path", "")
            if p == self.prefix or p.startswith(self.prefix + "/"):
                rest = p[len(self.prefix):] or "/"
                scope = dict(scope, path=rest,
                             root_path=(scope.get("root_path") or "") + self.prefix)
        await self.inner(scope, receive, send)


app = _PulsePrefixStrip(app)
