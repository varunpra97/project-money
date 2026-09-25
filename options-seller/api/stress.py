"""Volatility stress lab: test a shock against the paper book before a trade.

POST /api/stress/test with {"price_move_pct", "vol_jump_pct", "days_forward"}
prices every open paper position twice with Black-Scholes — once at current
market conditions, once under the shock (underlying moved by price_move_pct,
implied volatility scaled by vol_jump_pct, and days_forward days of time
decay) — and reports the per-position and portfolio P&L impact.

"Volatility stress lab" product upgrade: lets users see what a price move,
an IV jump, and one day of theta decay would do to their book *before*
opening a trade.

Market data (spot + per-symbol IV) comes from yfinance with a CBOE delayed-quotes
fallback (same resilient pattern as the /api/options chain proxy), cached 60s
in memory.
Legs are valued with the position's dte as time to expiry. Covered calls also
include the 100-shares-per-contract stock leg. A symbol that fails to resolve
is reported with a note and excluded from totals; the endpoint never 500s.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger("pulse.stress")

RISK_FREE = 0.045
_MULT = 100.0  # option contract multiplier

# ── tiny in-memory TTL cache for yfinance spot/IV per symbol ────────────────
_market_cache: dict[str, tuple[float, dict[str, Any]]] = {}
MARKET_TTL = 60.0


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_price(spot: float, strike: float, t_years: float, rate: float,
              vol: float, is_call: bool) -> float:
    """Black-Scholes price for one share (multiply by 100 for a contract)."""
    t = max(t_years, 1.0 / 365.0)
    vol = max(vol, 0.01)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    if is_call:
        return spot * _norm_cdf(d1) - strike * math.exp(-rate * t) * _norm_cdf(d2)
    return strike * math.exp(-rate * t) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def _market_yfinance(sym: str) -> dict[str, Any]:
    """Spot + near-the-money IV via yfinance. Empty fields when blocked."""
    out: dict[str, Any] = {"spot": None, "iv": None}
    try:
        import yfinance as yf
        t = yf.Ticker(sym)
        spot: Optional[float] = None
        try:
            spot = float(t.fast_info.last_price)
        except Exception:
            hist = t.history(period="5d")
            if hist is not None and not hist.empty:
                spot = float(hist["Close"].iloc[-1])
        out["spot"] = spot
        if spot and math.isfinite(spot):
            ivs: list[float] = []
            try:
                expiries = list(t.options or [])[:3]
                for exp in expiries:
                    chain = t.option_chain(exp)
                    for frame in (chain.calls, chain.puts):
                        if frame is None or frame.empty:
                            continue
                        near = frame[(frame["strike"] >= spot * 0.85)
                                     & (frame["strike"] <= spot * 1.15)]
                        for v in near.get("impliedVolatility", []):
                            try:
                                f = float(v)
                                if 0.05 < f < 3.0:
                                    ivs.append(f)
                            except (TypeError, ValueError):
                                pass
                    if ivs:
                        break
            except Exception:
                pass
            if ivs:
                ivs.sort()
                out["iv"] = ivs[len(ivs) // 2]
    except Exception:
        log.warning("stress: yfinance market data failed for %s", sym)
    return out


def _market_cboe(sym: str) -> dict[str, Any]:
    """CBOE 15-min delayed quotes fallback (cdn.cboe.com, no auth).

    Same source the /api/options chain proxy falls back to — reachable from
    datacenter IPs where Yahoo blocks yfinance."""
    import json as _json
    import re as _re
    import urllib.request

    out: dict[str, Any] = {"spot": None, "iv": None}
    try:
        url = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Pulse/1.0"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            if resp.status != 200:
                return out
            payload = _json.load(resp)
    except Exception:
        log.warning("stress: CBOE market data failed for %s", sym)
        return out
    data = (payload or {}).get("data") or {}
    try:
        spot = float(data.get("current_price"))
    except (TypeError, ValueError):
        return out
    if not (spot and math.isfinite(spot)):
        return out
    out["spot"] = spot
    ivs: list[float] = []
    for r in data.get("options") or []:
        m = _re.match(r"^(.+?)(\d{6})([CP])(\d{8})$", str(r.get("option") or ""))
        if not m:
            continue
        strike = int(m.group(4)) / 1000.0
        if strike < spot * 0.85 or strike > spot * 1.15:
            continue
        try:
            f = float(r.get("iv"))
            if 0.05 < f < 3.0:
                ivs.append(f)
        except (TypeError, ValueError):
            pass
    if ivs:
        ivs.sort()
        out["iv"] = ivs[len(ivs) // 2]
    return out


def _market(symbol: str) -> dict[str, Any]:
    """Spot price + near-the-money IV for a symbol (60s memory cache).

    yfinance first, CBOE delayed quotes fallback — mirrors the /api/options
    chain proxy so the lab works from datacenter IPs Yahoo blocks."""
    sym = symbol.upper()
    now = time.monotonic()
    hit = _market_cache.get(sym)
    if hit is not None and hit[0] > now:
        return hit[1]
    out = _market_yfinance(sym)
    if not out.get("spot") or not out.get("iv"):
        fallback = _market_cboe(sym)
        for k in ("spot", "iv"):
            if out.get(k) is None and fallback.get(k) is not None:
                out[k] = fallback[k]
    _market_cache[sym] = (now + MARKET_TTL, out)
    return out


def _clamp(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        f = float(v)
        if not math.isfinite(f):
            return default
        return max(lo, min(hi, f))
    except (TypeError, ValueError):
        return default


def _position_stress(pos: dict[str, Any], move_pct: float, vol_pct: float,
                     days_fwd: int) -> dict[str, Any]:
    underlying = str(pos.get("underlying") or "").upper()
    strategy = str(pos.get("strategy") or "")
    dte = _clamp(pos.get("dte"), 1, 365 * 3, 30)
    market = _market(underlying)
    spot = market.get("spot")
    iv = market.get("iv")
    base = {
        "id": pos.get("id"), "underlying": underlying,
        "strategy": strategy,
        "display_name": str(pos.get("display_name") or pos.get("strategy") or "—"),
        "base_value": None, "stressed_value": None,
        "pnl": None, "pnl_pct": None, "note": None,
    }
    if not spot or not iv:
        base["note"] = "Market data unavailable — excluded from totals."
        return base

    move = 1.0 + move_pct / 100.0
    vol_mult = max(1.0 + vol_pct / 100.0, 0.05)
    t_now = max(dte / 365.0, 1.0 / 365.0)
    t_fwd = max((dte - days_fwd) / 365.0, 1.0 / 365.0)
    spot_fwd = spot * move
    iv_fwd = iv * vol_mult

    base_val = 0.0
    fwd_val = 0.0
    legs = pos.get("legs") or []
    for leg in legs:
        side = str(leg.get("side") or "sell").lower()
        sign = 1.0 if side == "buy" else -1.0
        strike = float(leg.get("strike") or 0)
        qty = float(leg.get("quantity") or 1)
        if strike <= 0:
            continue
        is_call = str(leg.get("option_type") or "").lower() == "call"
        b = _bs_price(spot, strike, t_now, RISK_FREE, iv, is_call)
        f = _bs_price(spot_fwd, strike, t_fwd, RISK_FREE, iv_fwd, is_call)
        base_val += sign * qty * _MULT * b
        fwd_val += sign * qty * _MULT * f

    # Covered call: the stock leg moves 1:1 with the underlying.
    if strategy == "covered_call":
        qty = max(float((legs[0].get("quantity") if legs else 1) or 1), 1.0)
        base_val += qty * _MULT * spot
        fwd_val += qty * _MULT * spot_fwd

    pnl = fwd_val - base_val
    max_loss = pos.get("max_loss")
    denom = None
    try:
        ml = float(max_loss) if max_loss is not None else 0.0
        denom = ml if ml > 0 else float(pos.get("credit") or 0) or None
    except (TypeError, ValueError):
        denom = None
    pnl_pct = round(pnl / denom * 100.0, 1) if denom else None

    base.update({
        "base_value": round(base_val, 2),
        "stressed_value": round(fwd_val, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": pnl_pct,
    })
    return base


def run_stress_test(price_move_pct: Any = 0, vol_jump_pct: Any = 0,
                    days_forward: Any = 1) -> dict[str, Any]:
    """Shock the open paper book; returns per-position + portfolio impact."""
    move_pct = _clamp(price_move_pct, -50, 50, 0)
    vol_pct = _clamp(vol_jump_pct, 0, 300, 0)
    days_fwd = int(_clamp(days_forward, 0, 30, 1))

    from options_seller.portfolio.api import list_open, load_executor

    positions: list[dict[str, Any]] = []
    total_base = 0.0
    total_fwd = 0.0
    try:
        ex = load_executor()
        opens = [p for p in list_open(ex) if p.get("status") == "open"]
    except Exception:
        log.warning("stress: could not load open positions", exc_info=True)
        opens = []
    for p in opens:
        try:
            row = _position_stress(p, move_pct, vol_pct, days_fwd)
        except Exception:
            log.warning("stress: position %s failed", p.get("id"), exc_info=True)
            row = {"id": p.get("id"), "underlying": p.get("underlying"),
                   "strategy": p.get("strategy"),
                   "display_name": p.get("display_name") or "—",
                   "base_value": None, "stressed_value": None,
                   "pnl": None, "pnl_pct": None,
                   "note": "Could not value this position."}
        positions.append(row)
        if row["pnl"] is not None:
            total_base += row["base_value"] or 0.0
            total_fwd += row["stressed_value"] or 0.0

    return {
        "scenario": {"price_move_pct": move_pct, "vol_jump_pct": vol_pct,
                     "days_forward": days_fwd},
        "as_of": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "base_value": round(total_base, 2),
            "stressed_value": round(total_fwd, 2),
            "pnl": round(total_fwd - total_base, 2),
        },
        "positions": positions,
        "paper_trading_only": True,
    }
