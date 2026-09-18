"""Payoff-at-expiration curves for multi-leg option positions."""

from __future__ import annotations

from typing import Any, Optional


def _leg_payoff(leg: dict[str, Any], spot: float) -> float:
    """Intrinsic payoff for one option/stock leg at expiration (per contract * qty * 100)."""
    side = (leg.get("side") or "sell").lower()
    qty = int(leg.get("quantity") or 1)
    opt = (leg.get("option_type") or "").lower()
    strike = leg.get("strike")
    sign = -1.0 if side in ("sell", "short") else 1.0

    if opt in ("", "stock", "shares") or strike is None:
        # Stock: approximate long shares if side buy
        # For covered call underlying, treat as 100 shares long when side=buy
        if opt in ("stock", "shares") or (strike is None and opt == ""):
            # Ignore bare stock in payoff unless explicit — covered call strategies
            # usually only list the short call in legs for this package.
            return 0.0
        return 0.0

    k = float(strike)
    if opt == "put":
        intrinsic = max(k - spot, 0.0)
    elif opt == "call":
        intrinsic = max(spot - k, 0.0)
    else:
        return 0.0
    return sign * intrinsic * 100.0 * qty


def payoff_at_expiration(position: dict[str, Any], spot: float) -> float:
    """Total P/L at expiration for ``spot`` underlying price.

    Includes original credit received (credit trades) or debit paid.
    """
    credit = position.get("credit")
    credit_debit = position.get("credit_debit") or "credit"
    premium = float(credit or 0.0)
    if credit_debit == "debit":
        premium = -abs(premium)

    legs_pnl = sum(_leg_payoff(leg, spot) for leg in position.get("legs") or [])
    return round(premium + legs_pnl, 2)


def breakevens(position: dict[str, Any], lo: float, hi: float, steps: int = 400) -> list[float]:
    """Approximate spot prices where payoff crosses zero."""
    if hi <= lo:
        return []
    xs = [lo + (hi - lo) * i / steps for i in range(steps + 1)]
    ys = [payoff_at_expiration(position, x) for x in xs]
    bes: list[float] = []
    for i in range(1, len(ys)):
        if ys[i - 1] == 0:
            bes.append(xs[i - 1])
        elif ys[i - 1] * ys[i] < 0:
            # linear interpolate
            t = abs(ys[i - 1]) / (abs(ys[i - 1]) + abs(ys[i]))
            bes.append(xs[i - 1] + t * (xs[i] - xs[i - 1]))
    return bes


def payoff_series(
    position: dict[str, Any],
    *,
    center: float | None = None,
    span_pct: float = 0.20,
    points: int = 120,
) -> dict[str, Any]:
    """Build x/y series for Plotly risk chart plus max profit/loss and breakevens."""
    strikes = [
        float(leg["strike"])
        for leg in position.get("legs") or []
        if leg.get("strike") is not None
    ]
    ref = center
    if ref is None:
        ref = position.get("underlying_mark") or position.get("underlying_price_at_open")
    if ref is None and strikes:
        ref = sum(strikes) / len(strikes)
    if ref is None or ref <= 0:
        ref = 100.0

    lo = ref * (1.0 - span_pct)
    hi = ref * (1.0 + span_pct)
    if strikes:
        lo = min(lo, min(strikes) * 0.92)
        hi = max(hi, max(strikes) * 1.08)

    xs = [lo + (hi - lo) * i / max(points - 1, 1) for i in range(points)]
    ys = [payoff_at_expiration(position, x) for x in xs]
    max_profit = position.get("max_profit")
    max_loss = position.get("max_loss")
    if max_profit is None and ys:
        max_profit = max(ys)
    if max_loss is None and ys:
        # max_loss stored as positive magnitude in plans; chart uses signed PnL
        max_loss = abs(min(ys))

    return {
        "spots": xs,
        "pnl": ys,
        "center": ref,
        "breakevens": breakevens(position, lo, hi),
        "max_profit": max_profit,
        "max_loss": max_loss,
        "strikes": strikes,
    }
