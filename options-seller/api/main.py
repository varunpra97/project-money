"""FastAPI backend for the mobile trading-insights app.

EDUCATIONAL / PAPER TRADING ONLY — this API never places live orders. It reads
the same paper-trading store and scan data as the Streamlit dashboard
(dashboard/app.py) and exposes it as low-latency JSON for a mobile frontend.

Aggressive in-memory TTL caching keeps cached responses well under 50ms.
Yahoo Finance is never hammered: market_signals.py keeps its own 6h file
cache, and /api/quote caches per range.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import re
import math
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
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

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from options_seller.config import load_defaults
from options_seller.models.scanner import PortfolioContext
from options_seller.portfolio.api import (
    days_held,
    list_open,
    load_executor,
    pct_of_max_profit,
    portfolio_greeks_est,
    summary_metrics,
)
from options_seller.portfolio.scanner_feed import build_candidates, load_scan_envelope as _load_scan_envelope
from options_seller.paths import data_dir

from options_seller.risk.limits import evaluate_book, risk_limits_from_config

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
if _signals:
    _signals.CACHE_PATH = data_dir() / "market_signals_cache.json"
_signals_lock = threading.Lock()


def load_scan_envelope():
    # Production clients must never silently substitute the example fixture.
    return _load_scan_envelope(allow_example=False)

# ── In-memory TTL cache ──────────────────────────────────────────────────────
_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()
_key_locks: dict[str, threading.Lock] = {}


def cached(ttl: int, key: str, fn: Callable[[], Any]) -> Any:
    """Return cached value if fresh, else compute, store and return it."""
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]
    # Coalesce concurrent misses so clients share a single upstream fetch.
    with _cache_lock:
        key_lock = _key_locks.setdefault(key, threading.Lock())
    with key_lock:
        with _cache_lock:
            hit = _cache.get(key)
            if hit is not None and hit[0] > time.monotonic():
                return hit[1]
        val = fn()
        if isinstance(val, dict) and "error" in val:
            return val
        with _cache_lock:
            _cache[key] = (time.monotonic() + ttl, val)
        return val


def _api(fn):
    """Never 500 on data problems: return structured JSON with an error field."""

    if asyncio.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            try: return await fn(*args, **kwargs)
            except Exception as e:
                return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=502)
        return async_wrapper

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - deliberate graceful degradation
            return JSONResponse(
                {"error": f"{type(e).__name__}: {e}"}, status_code=502
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
        value = float(v)
        return round(value, 2) if math.isfinite(value) else None
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
@asynccontextmanager
async def lifespan(app):
    async def observe():
        while True:
            try:
                await asyncio.to_thread(performance)
                def tracked_symbols():
                    return [p.get("underlying", "") for p in load_executor().list_open()]
                for symbol in await asyncio.to_thread(tracked_symbols):
                    if symbol:
                        live_prices.wanted[symbol.upper()] = time.time()
                        await quote(symbol, "1d", False)
            except Exception:
                logging.exception("Unable to record paper performance snapshot")
            await asyncio.sleep(60)
    live_prices.task = asyncio.create_task(live_prices.run())
    quote_cache.worker = asyncio.create_task(quote_cache.maintain())
    task = asyncio.create_task(observe())
    collector = asyncio.create_task(collect_client_data())
    yield
    collector.cancel()
    await asyncio.gather(collector, return_exceptions=True)
    await live_prices.stop()
    await quote_cache.close()
    if bridge.proc and bridge.proc.returncode is None:
        bridge.proc.terminate()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="Options Seller Mobile API", version="1.1.0", lifespan=lifespan)

# Clients (iOS / Android / web) may call this API cross-origin when using a
# dedicated backend base URL. Streamlit dashboards stay same-origin via Caddy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)



@app.get("/api/health")
def health():
    """Liveness + coarse dependency flags for mobile/ops."""
    scan_ok = False
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8080/api/scan", timeout=2) as r:
            scan_ok = r.status == 200
    except Exception:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8502/api/scan", timeout=2) as r:
                scan_ok = r.status == 200
        except Exception:
            scan_ok = False
    return {
        "ok": True,
        "service": "pulse-api",
        "version": "1.1.0",
        "paper_trading_only": True,
        "scan_feed_reachable": scan_ok,
        "as_of": _now_iso(),
    }


@app.get("/api/risk/status")
@_api
def risk_status():
    """$50k max portfolio risk hard cap (paper book). Soft warn at 80%."""

    def _build():
        ex = load_executor()
        opens = [p for p in list_open(ex) if p.get("status") == "open"]
        lim = risk_limits_from_config()
        book = evaluate_book(opens, lim)
        book["as_of"] = _now_iso()
        book["paper_trading_only"] = True
        return book

    return cached(15, "risk:status", _build)


@app.get("/api/scan")
@_api
def scan_proxy():
    """Same scan envelope as Caddy /api/scan — one baseURL for mobile clients."""

    def _build():
        import json
        import urllib.request

        # A prepared server file is the quickest source; do not probe two services first.
        env, status = _load_scan_envelope(try_remote=False, allow_example=False)
        if env is not None:
            payload = {**env.model_dump(mode="json", by_alias=True), "feed_status": status}
            theta = thetahedge_load()
            if theta:
                trows = theta.get("rows", {})
                for res in payload.get("results", []):
                    t = trows.get((res.get("symbol") or "").upper())
                    if t:
                        res["theta"] = t
            return payload
        for url in (
            "http://127.0.0.1:8080/api/scan",
            "http://127.0.0.1:8502/api/scan",
        ):
            try:
                with urllib.request.urlopen(url, timeout=8) as r:
                    return json.loads(r.read().decode("utf-8"))
            except Exception:
                continue
        # Fall back to on-disk envelope used by dashboard
        env, status = load_scan_envelope()
        if env is not None:
            return {**env.model_dump(mode="json", by_alias=True), "feed_status": status}
        return {"error": "scan_unavailable", "schema": "stock-data-scanner.scan/v0.1"}

    return cached(30, "scan:proxy", _build)


@app.get("/api/thetahedge")
@_api
def thetahedge_top(limit: int = Query(50, ge=1, le=500)):
    """ThetaHedge volatility rankings — best risk/reward for selling options.

    Sorted by wheel_rank ascending (rank 1 = best). Refreshed once a day by
    the thetahedge_daily collector; served from the saved file here.
    """

    def _build():
        data = thetahedge_load()
        if not data:
            return {"as_of": None, "total": 0, "rows": [],
                    "error": "thetahedge_unavailable"}
        rows = [r for r in data.get("rows", {}).values()
                if (r.get("wheel_rank") or 0) > 0]
        rows.sort(key=lambda r: r["wheel_rank"])
        return {"as_of": data.get("asOf"), "total": len(rows),
                "rows": rows[:limit]}

    return cached(3600, f"thetahedge:top:{limit}", _build)


_thetahedge_refresh_lock = threading.Lock()
_thetahedge_refresh_last: float = 0.0


@app.post("/api/thetahedge/refresh")
@_api
def thetahedge_refresh():
    """Kick off a ThetaHedge recollect in the background (admin/ops use).

    Guarded by a lock and a 15-minute cooldown so it can't be used to hammer
    ThetaHedge's API. Returns immediately; poll /api/thetahedge for results.
    """
    global _thetahedge_refresh_last
    with _thetahedge_refresh_lock:
        now = time.time()
        if now - _thetahedge_refresh_last < 900:
            return {"status": "cooldown",
                    "retry_in_seconds": int(900 - (now - _thetahedge_refresh_last))}
        _thetahedge_refresh_last = now

    def _run():
        try:
            thetahedge_collect()
        except Exception:
            logging.exception("ThetaHedge manual refresh failed")

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started"}


@app.get("/api/breaches")
@_api
def breaches_latest():
    """S&P 500 stocks (watchlist-19 excluded) that breached a technical level
    in the past few trading days — 50-day SMA crosses and 20-day high/low
    breaks, each with direction. Refreshed daily by the breaches worker;
    served from the saved file here.
    """

    def _build():
        data = breaches_load()
        if not data:
            return {"as_of": None, "total": 0, "results": [],
                    "error": "breaches_unavailable"}
        return {"as_of": data.get("asOf"), "total": data.get("total", 0),
                "window_days": data.get("window_days"),
                "results": data.get("results", [])}

    return cached(3600, "breaches:latest", _build)


_breaches_refresh_lock = threading.Lock()
_breaches_refresh_last: float = 0.0


@app.post("/api/breaches/refresh")
@_api
def breaches_refresh():
    """Kick off a breach-scan recollect in the background (admin/ops use).

    Guarded by a lock and a 15-minute cooldown. Returns immediately;
    poll /api/breaches for results.
    """
    global _breaches_refresh_last
    with _breaches_refresh_lock:
        now = time.time()
        if now - _breaches_refresh_last < 900:
            return {"status": "cooldown",
                    "retry_in_seconds": int(900 - (now - _breaches_refresh_last))}
        _breaches_refresh_last = now

    def _run():
        try:
            breaches_collect()
        except Exception:
            logging.exception("Breaches manual refresh failed")

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started"}


# ── Upgrade builder ("Build this upgrade" in the app's Product lab) ──────────

@app.post("/api/upgrades/request")
@_api
def upgrades_request(body: dict):
    """File an upgrade request from a Product lab idea. Refused (409) while
    another upgrade is active — upgrades run one at a time."""
    try:
        job = upgrades_create({
            "idea_id": body.get("idea_id", ""),
            "title": body.get("title", ""),
            "detail": body.get("detail", ""),
            "measure": body.get("measure", ""),
            "effort": body.get("effort", ""),
        })
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=409)
    return job


@app.get("/api/upgrades/active")
@_api
def upgrades_active():
    """Latest upgrade job of any status — what the app polls to render the
    Build/Undo button state."""
    job = upgrades_latest()
    return {"job": job, "store": upgrades_store()}


@app.get("/api/upgrades/pending")
@_api
def upgrades_pending():
    """Pending requests plus undo requests — polled by the builder worker."""
    return {"pending": upgrades_pending_jobs(),
            "undo_requested": upgrades_undo_requested()}


@app.post("/api/upgrades/{job_id}/claim")
@_api
def upgrades_claim(job_id: str):
    job = upgrades_claim_job(job_id)
    if job is None:
        return JSONResponse({"error": "job not found or not pending"},
                            status_code=404)
    return job


@app.post("/api/upgrades/{job_id}/complete")
@_api
def upgrades_complete(job_id: str, body: dict):
    job = upgrades_complete_job(job_id, str(body.get("commit_sha", "")))
    if job is None:
        return JSONResponse({"error": "job not found or not building"},
                            status_code=404)
    return job


@app.post("/api/upgrades/{job_id}/fail")
@_api
def upgrades_fail(job_id: str, body: dict):
    job = upgrades_fail_job(job_id, str(body.get("error", "unknown error")))
    if job is None:
        return JSONResponse({"error": "job not found or already terminal"},
                            status_code=404)
    return job


@app.post("/api/upgrades/{job_id}/request-undo")
@_api
def upgrades_request_undo(job_id: str):
    job = upgrades_request_undo_job(job_id)
    if job is None:
        return JSONResponse({"error": "job not found or not deployed"},
                            status_code=404)
    return job


@app.post("/api/upgrades/{job_id}/start-undo")
@_api
def upgrades_start_undo(job_id: str):
    job = upgrades_start_undo_job(job_id)
    if job is None:
        return JSONResponse({"error": "job not found or undo not requested"},
                            status_code=404)
    return job


@app.post("/api/upgrades/{job_id}/complete-undo")
@_api
def upgrades_complete_undo(job_id: str, body: dict):
    job = upgrades_complete_undo_job(job_id, str(body.get("revert_sha", "")))
    if job is None:
        return JSONResponse({"error": "job not found or undo not started"},
                            status_code=404)
    return job


@app.get("/api/events")
@_api
def events_endpoint(symbols: str = ""):
    """Upcoming earnings, ex-dividend, and FOMC decision dates for symbols.

    Used by the iOS app to show event risk beside open positions.
    Never fails the request — an unresolvable symbol just gets empty dates.
    """
    return events_get(symbols)


@app.post("/api/stress/test")
@_api
def stress_endpoint(body: dict):
    """Volatility stress lab: test a price move, an IV jump, and time decay
    against the open paper book before opening a trade. Never fails the
    request — unresolvable symbols are reported with a note."""
    return stress_run(
        price_move_pct=body.get("price_move_pct", 0),
        vol_jump_pct=body.get("vol_jump_pct", 0),
        days_forward=body.get("days_forward", 1),
    )


def _brokerage_unauthorized():
    return JSONResponse({"error": "unauthorized"}, status_code=401)


@app.post("/api/brokerage/sync")
@_api
def brokerage_sync(body: dict, request: Request):
    """Ingest a Plaid holdings snapshot from the assistant VM's sync job.
    Auth: X-Sync-Token == BROKERAGE_SYNC_TOKEN."""
    if not brokerage_sync_ok(request.headers.get("x-sync-token")):
        return _brokerage_unauthorized()
    return brokerage_save(body or {})


def _brokerage_snapshot_or_404():
    snap = brokerage_load()
    if not snap:
        return None, JSONResponse({"error": "no brokerage snapshot synced yet"},
                                  status_code=404)
    return snap, None


@app.get("/api/brokerage/positions")
@_api
def brokerage_positions(request: Request):
    """Real open positions, mapped to the portfolio position shape.
    Auth: X-App-Token == APP_READ_TOKEN."""
    if not brokerage_app_ok(request.headers.get("x-app-token")):
        return _brokerage_unauthorized()
    snap, err = _brokerage_snapshot_or_404()
    if err:
        return err
    return {"positions": snap.get("positions") or [],
            "as_of": snap.get("synced_at")}


@app.get("/api/brokerage/summary")
@_api
def brokerage_summary(request: Request):
    """Account summary for the real book. Auth: X-App-Token."""
    if not brokerage_app_ok(request.headers.get("x-app-token")):
        return _brokerage_unauthorized()
    snap, err = _brokerage_snapshot_or_404()
    if err:
        return err
    return snap.get("summary") or {}


@app.get("/api/brokerage/status")
@_api
def brokerage_status(request: Request):
    """Sync health for the real book. Auth: X-App-Token."""
    if not brokerage_app_ok(request.headers.get("x-app-token")):
        return _brokerage_unauthorized()
    snap = brokerage_load()
    if not snap:
        return {"synced": False}
    return {"synced": True,
            "synced_at": snap.get("synced_at"),
            "positions": len(snap.get("positions") or []),
            "holdings": len(snap.get("holdings") or [])}


@app.post("/api/brokerage/stress/test")
@_api
def brokerage_stress_endpoint(body: dict, request: Request):
    """Volatility stress lab against the real book. Auth: X-App-Token."""
    if not brokerage_app_ok(request.headers.get("x-app-token")):
        return _brokerage_unauthorized()
    try:
        return brokerage_stress_run(
            price_move_pct=body.get("price_move_pct", 0),
            vol_jump_pct=body.get("vol_jump_pct", 0),
            days_forward=body.get("days_forward", 1),
        )
    except LookupError:
        return JSONResponse({"error": "no brokerage snapshot synced yet"},
                            status_code=404)


@app.get("/api/version")
@_api
def version():
    """Deployed commit — lets the builder worker confirm a Render redeploy
    landed before marking an upgrade deployed."""
    return {"git_sha": os.environ.get("RENDER_GIT_COMMIT"),
            "service": "pulse-backend"}


@app.get("/api/portfolio/summary")
@_api
def portfolio_summary():
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
def portfolio_positions():
    def _build():
        ex = load_executor()
        rows = []
        for p in ex.list_open():
            if p.get("status") != "open":
                continue
            legs = p.get("legs") or []
            expirations = sorted({str(leg["expiry"]) for leg in legs if leg.get("expiry")})
            premium = _num(p.get("credit"))
            mark = _num(p.get("mark"))
            credit_trade = p.get("credit_debit", "credit") == "credit"
            rows.append(
                {
                    "id": p.get("id"),
                    "underlying": p.get("underlying"),
                    "strategy": p.get("strategy"),
                    "display_name": _strat_name(p.get("strategy")),
                    "opened_at": p.get("opened_at"),
                    "dte": p.get("dte"),
                    "expiry": p.get("expiry") or (expirations[0] if len(expirations) == 1 else None),
                    "opening_value": abs(premium) if premium is not None else None,
                    "close_value": abs(mark) if mark is not None else None,
                    "premium_direction": "credit" if credit_trade else "debit",
                    "mark_as_of": p.get("marked_at"),
                    "day_pnl": None,  # No prior-day option marks are recorded.
                    "return_pct": (float(p["unrealized_pnl"]) / abs(float(p["credit"])) * 100
                                   if p.get("unrealized_pnl") is not None and p.get("credit") else None),
                    "equity": (abs(mark) * (-1 if credit_trade else 1) if mark is not None else None),
                    "legs": [{key: leg.get(key) for key in ("side", "option_type", "strike", "quantity", "expiry")} for leg in legs],
                    "qty": _contract_qty(legs),
                    "credit": _num(p.get("credit")),
                    "unrealized": _num(p.get("unrealized_pnl")),
                    "pct_of_max_profit": _num(
                        pct_of_max_profit(p.get("unrealized_pnl"), p.get("max_profit"))
                    ),
                    "days_held": _num(days_held(p.get("opened_at"), p.get("closed_at"))),
                    "risk_label": _risk_label(p),
                    "max_loss": _num(p.get("max_loss")),
                    "max_profit": _num(p.get("max_profit")),
                }
            )
        return {"positions": rows, "as_of": _now_iso()}

    return cached(30, "portfolio:positions", _build)


@app.get("/api/portfolio/activity")
@_api
def portfolio_activity():
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
def insights_celebrity():
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
    with _signals_lock:
        data_dir().mkdir(parents=True, exist_ok=True)
        return _signals.get_market_signals(symbols)


@app.get("/api/insights/earnings")
@_api
def insights_earnings():
    def _build():
        symbols = _celeb_symbols()
        if _signals is None or not symbols:
            return {"as_of": _now_iso(), "fresh": False, "rows": [], "warning": "market signals module not available"}
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
def insights_volatility():
    def _build():
        symbols = _celeb_symbols()
        if _signals is None or not symbols:
            return {"as_of": _now_iso(), "fresh": False, "rows": [], "warning": "market signals module not available"}
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
def candidates():
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
    "1d": ("1d", "1m", 20),
    "5d": ("5d", "15m", 20),
    "1mo": ("1mo", "1d", 20),
    "3mo": ("3mo", "1d", 20),
    "1y": ("1y", "1d", 20),
}


@app.get("/api/quote/{symbol}")
@_api
async def quote(symbol: str, range: str = Query("1d"), refresh: bool = False):
    rng = str(range or "1d").lower()
    if rng not in _QUOTE_RANGES:
        return {"error": f"range must be one of {sorted(_QUOTE_RANGES)}"}
    period, interval, ttl = _QUOTE_RANGES[rng]
    sym = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=-]{0,19}", sym):
        raise ValueError("Invalid ticker symbol")

    def _build():
        import yfinance as yf

        df = yf.download(sym, period=period, interval=interval, progress=False,
                         auto_adjust=True, timeout=12, threads=False)
        if df is None or len(df) == 0:
            raise ValueError(f"No price history returned for {sym}. Check the ticker or retry; the provider may be unavailable.")
        # yfinance >= 1.x may return MultiIndex columns even for one ticker
        if hasattr(df.columns, "levels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
        closes = df["Close"].dropna() if "Close" in df.columns else df.iloc[:, 0].dropna()
        bars = []
        for ts, row in df.iterrows():
            values = {key: float(row[column]) for key, column in
                      [("o", "Open"), ("h", "High"), ("l", "Low"), ("c", "Close")]}
            if not all(math.isfinite(v) for v in values.values()):
                continue
            volume = float(row.get("Volume", 0))
            bars.append({"t": int(ts.timestamp()), **{k: round(v, 4) for k, v in values.items()},
                         "v": max(0, int(volume)) if math.isfinite(volume) else 0})
        if not bars:
            raise ValueError(f"No complete OHLC bars available for {sym}")
        first, last = bars[0]["c"], bars[-1]["c"]
        return {
            "symbol": sym,
            "price": round(last, 2),
            "chg_pct": round((last - first) / first * 100, 2) if first else 0.0,
            "bars": bars,
            "as_of": datetime.fromtimestamp(bars[-1]["t"], timezone.utc).isoformat(),
            "source": "Yahoo Finance",
            "interval": interval,
        }

    return await quote_cache.get(f"quote:{sym}:{rng}", _build, ttl=ttl, force=refresh)


@app.get("/api/options/{symbol}")
@_api
def options_chain(symbol: str, dte: int = Query(14, ge=1, le=90)):
    """Options chain for the 3 expirations nearest `dte` (default ~14 DTE).

    The iOS app used to hit Yahoo's options API directly, but Yahoo now
    requires crumb auth (401 without it); yfinance handles that server-side.
    Yahoo's v7 options API also blocks some datacenter IPs, so when yfinance
    comes back empty we fall back to CBOE's public 15-min delayed quotes
    (cdn.cboe.com, no auth). Strikes trimmed to ±30% of spot to keep the
    payload small. Cached 120s.
    """
    sym = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=-]{0,19}", sym):
        raise ValueError("Invalid ticker symbol")

    def _cboe_chain():
        """CBOE delayed quotes fallback. Returns None when unavailable."""
        import json as _json
        import urllib.request
        from datetime import date as _date

        url = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Pulse/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                if resp.status != 200:
                    return None
                payload = _json.load(resp)
        except Exception:
            return None
        data = (payload or {}).get("data") or {}
        raw = data.get("options") or []
        try:
            spot = float(data.get("current_price"))
        except (TypeError, ValueError):
            spot = None
        today = _date.today()
        by_exp: dict = {}
        for r in raw:
            m = re.match(r"^(.+?)(\d{6})([CP])(\d{8})$", str(r.get("option") or ""))
            if not m:
                continue
            try:
                exp = _date(2000 + int(m.group(2)[:2]),
                            int(m.group(2)[2:4]), int(m.group(2)[4:6]))
            except ValueError:
                continue
            strike = int(m.group(4)) / 1000.0
            if spot and (strike < spot * 0.7 or strike > spot * 1.3):
                continue

            def _f(k):
                try:
                    v = float(r.get(k))
                    return v if math.isfinite(v) else None
                except (TypeError, ValueError):
                    return None

            contract = {"strike": strike, "bid": _f("bid"), "ask": _f("ask"),
                        "last": _f("last_trade_price"), "iv": _f("iv"),
                        "vol": _f("volume"), "oi": _f("open_interest")}
            grp = by_exp.setdefault(exp, {"calls": [], "puts": []})
            grp["calls" if m.group(3) == "C" else "puts"].append(contract)
        if not by_exp:
            return None

        def _dte(d):
            return (d - today).days

        picked = sorted(by_exp, key=lambda d: abs(_dte(d) - dte))[:3]
        out = []
        for exp in sorted(picked):
            grp = by_exp[exp]
            grp["calls"].sort(key=lambda c: c["strike"])
            grp["puts"].sort(key=lambda c: c["strike"])
            out.append({"date": exp.isoformat(), "dte": _dte(exp),
                        "calls": grp["calls"], "puts": grp["puts"]})
        return {"symbol": sym, "as_of": _now_iso(),
                "source": "CBOE (15-min delayed)",
                "underlying_price": spot, "expirations": out}

    def _yfinance_chain():
        import yfinance as yf
        from datetime import date

        t = yf.Ticker(sym)
        try:
            expirations = t.options or []
        except Exception as exc:
            return {"error": f"options_unavailable: {exc}", "symbol": sym}
        if not expirations:
            return {"error": "options_unavailable: no expirations", "symbol": sym}
        today = date.today()

        def _dte(dstr: str) -> int:
            try:
                return (date.fromisoformat(dstr) - today).days
            except ValueError:
                return 10 ** 6

        exps = sorted(expirations, key=lambda d: abs(_dte(d) - dte))[:3]
        try:
            spot = float(t.fast_info.get("lastPrice") or 0) or None
        except Exception:
            spot = None
        out = []
        for dstr in exps:
            try:
                chain = t.option_chain(dstr)
            except Exception:
                continue

            def _slim(df):
                rows = []
                for _, r in df.iterrows():
                    try:
                        strike = float(r["strike"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if spot and (strike < spot * 0.7 or strike > spot * 1.3):
                        continue

                    def _f(k):
                        try:
                            v = float(r[k])
                            return v if math.isfinite(v) else None
                        except (KeyError, TypeError, ValueError):
                            return None

                    rows.append({
                        "strike": strike,
                        "bid": _f("bid"), "ask": _f("ask"), "last": _f("lastPrice"),
                        "iv": _f("impliedVolatility"),
                        "vol": _f("volume"), "oi": _f("openInterest"),
                    })
                rows.sort(key=lambda r: r["strike"])
                return rows

            out.append({"date": dstr, "dte": _dte(dstr),
                        "calls": _slim(chain.calls), "puts": _slim(chain.puts)})
        if not out:
            return {"error": "options_unavailable: chain fetch failed", "symbol": sym}
        return {"symbol": sym, "as_of": _now_iso(), "source": "Yahoo Finance",
                "underlying_price": spot, "expirations": out}

    def _build():
        res = _yfinance_chain()
        if res.get("expirations"):
            return res
        cboe = _cboe_chain()
        return cboe if cboe else res

    return cached(120, f"options:{sym}:{dte}", _build)


_STATS_POOL = ThreadPoolExecutor(max_workers=4)

@app.get("/api/symbol/{symbol}")
@_api
def symbol_details(symbol: str, refresh: bool = False):
    sym = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=-]{0,19}", sym):
        raise ValueError("Invalid ticker symbol")
    def build():
        import yfinance as yf
        warnings = []
        earning_future = _STATS_POOL.submit(_signals._earnings_dates, sym, datetime.now(timezone.utc).date()) if _signals else None
        vol = {}
        try:
            bars = yf.Ticker(sym).history(period="3mo", interval="1d", auto_adjust=True, timeout=12)
            vol = _signals.compute_volatility(bars) if _signals is not None else {}
            if not vol: warnings.append("Not enough daily history for volatility statistics.")
        except Exception:
            warnings.append("Daily price history is temporarily unavailable.")
        earning = None
        if earning_future:
            try:
                e = _signals.classify_earnings(earning_future.result(timeout=5))
                date = e.get("upcoming") or e.get("last_reported")
                days = e.get("days_to")
                if date:
                    earning = {"symbol":sym,"company":sym,"earnings_date":str(date),"when":f"in {days} days" if days is not None else "last reported","status":"upcoming" if days is not None else "reported"}
                else: warnings.append("The provider has no earnings date for this ticker (common for ETFs and indices).")
            except Exception:
                earning_future.cancel()
                warnings.append("Earnings lookup timed out or is unavailable.")
        return {"symbol":sym,"as_of":_now_iso(),"source":"Yahoo Finance · may be delayed","volatility":{"symbol":sym,"company":sym,**vol} if vol else None,"earnings":earning,"warnings":warnings}
    if refresh:
        with _cache_lock: _cache.pop(f"symbol:{sym}",None)
    return cached(60,f"symbol:{sym}",build)


# Performance and news use sync routes so disk/network work runs off the event loop.
try:
    from .analytics import performance
    from .news import news_feed
    from .ideas import like_idea
except ImportError:  # startup script runs from api/
    from analytics import performance
    from news import news_feed
    from ideas import like_idea


@app.get("/api/performance")
def performance_endpoint(period: str = Query("lifetime", pattern="^(lifetime|week|month|quarter)$")):
    return performance(period)


@app.get("/api/news")
def news_endpoint(refresh: bool = False):
    return news_feed(refresh=refresh)


@app.post("/api/ideas/{idea_id}/like")
@_api
def idea_like(idea_id: str):
    """"I like it" on a deployed upgrade: drop the suggestion from the
    Product lab queue; the queue refills from the backlog."""
    like_idea(idea_id)
    return {"ok": True, "idea_id": idea_id}


try:
    from .assistant import router as assistant_router, bridge
    from .live import router as live_router, live_prices
    from .cache import quote_cache
    from .history import router as history_router
except ImportError:
    from assistant import router as assistant_router, bridge
    from live import router as live_router, live_prices
    from cache import quote_cache
    from history import router as history_router
app.include_router(assistant_router)
app.include_router(live_router)
app.include_router(history_router)

try:
    from .data_status import catalog
    from .collect_scan import collect as collect_scan
    from .thetahedge import collect as thetahedge_collect, load as thetahedge_load
    from .breaches import collect as breaches_collect, load as breaches_load
    from .events import get_events as events_get
    from .stress import run_stress_test as stress_run
    from .stress import run_brokerage_stress_test as brokerage_stress_run
    from .brokerage import (
        save_snapshot as brokerage_save,
        load_snapshot as brokerage_load,
        sync_token_ok as brokerage_sync_ok,
        app_token_ok as brokerage_app_ok,
    )
    from .upgrades import (
        create_job as upgrades_create,
        latest_job as upgrades_latest,
        pending_jobs as upgrades_pending_jobs,
        undo_requested_jobs as upgrades_undo_requested,
        claim as upgrades_claim_job,
        complete as upgrades_complete_job,
        fail as upgrades_fail_job,
        request_undo as upgrades_request_undo_job,
        start_undo as upgrades_start_undo_job,
        complete_undo as upgrades_complete_undo_job,
        store as upgrades_store,
    )
except ImportError:
    from data_status import catalog
    from collect_scan import collect as collect_scan
    from thetahedge import collect as thetahedge_collect, load as thetahedge_load
    from breaches import collect as breaches_collect, load as breaches_load
    from events import get_events as events_get
    from stress import run_stress_test as stress_run
    from stress import run_brokerage_stress_test as brokerage_stress_run
    from brokerage import (
        save_snapshot as brokerage_save,
        load_snapshot as brokerage_load,
        sync_token_ok as brokerage_sync_ok,
        app_token_ok as brokerage_app_ok,
    )
    from upgrades import (
        create_job as upgrades_create,
        latest_job as upgrades_latest,
        pending_jobs as upgrades_pending_jobs,
        undo_requested_jobs as upgrades_undo_requested,
        claim as upgrades_claim_job,
        complete as upgrades_complete_job,
        fail as upgrades_fail_job,
        request_undo as upgrades_request_undo_job,
        start_undo as upgrades_start_undo_job,
        complete_undo as upgrades_complete_undo_job,
        store as upgrades_store,
    )


async def collect_client_data():
    """Prepare non-tick datasets on the server even while no clients are open."""
    async def metadata():
        while True:
            await catalog.collect({"summary": portfolio_summary, "positions": portfolio_positions,
                "activity": portfolio_activity, "risk": risk_status, "news": news_endpoint,
                "celebrity": insights_celebrity, "earnings": insights_earnings,
                "volatility": insights_volatility, "candidates": candidates})
            for period in ("lifetime", "week", "month", "quarter"):
                await catalog.collect({"performance:"+period: lambda p=period: performance(p)})
            await asyncio.sleep(300)
    async def scanner():
        while True:
            if os.environ.get("PULSE_SCAN_COLLECTOR", "0") == "1":
                await catalog.collect({"scan": collect_scan})
                with _cache_lock:
                    _cache.pop("scan:proxy", None)
                    _cache.pop("candidates", None)
            else:
                await catalog.collect({"scan": scan_proxy})
            await asyncio.sleep(300)
    async def thetahedge_daily():
        # ThetaHedge rankings refresh once a day (their table updates every
        # 5 min during market hours; daily is plenty for our universe).
        # Retry hourly until the first successful pull — the API throttles
        # bursts, so a boot-time failure should heal on its own.
        first_ok = False
        while True:
            try:
                await asyncio.to_thread(thetahedge_collect)
                first_ok = True
            except Exception:
                logging.exception("ThetaHedge daily collect failed")
            await asyncio.sleep(86400 if first_ok else 3600)
    async def breaches_daily():
        # Breach scan refreshes once a day — "past few days" doesn't need
        # intraday. Retry hourly until the first successful pull so a
        # boot-time Yahoo hiccup heals on its own.
        first_ok = False
        while True:
            try:
                await asyncio.to_thread(breaches_collect)
                first_ok = True
            except Exception:
                logging.exception("Breaches daily collect failed")
            await asyncio.sleep(86400 if first_ok else 3600)
    workers = [asyncio.create_task(metadata()), asyncio.create_task(scanner()),
               asyncio.create_task(thetahedge_daily()),
               asyncio.create_task(breaches_daily())]
    try:
        await asyncio.gather(*workers)
    finally:
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


@app.get("/api/data/status")
def data_status():
    return catalog.snapshot()

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
