"""Compatibility shim — prefer options_seller.risk.limits / enforce."""

from __future__ import annotations

from typing import Any, Callable, Optional

from options_seller.risk.limits import (
    RiskLimits,
    aggregate_open_risk,
    evaluate_book,
    position_risk,
)
from options_seller.risk.enforce import enforce_hard_limits

HARD_CAP_USD = 50_000.0
SOFT_WARN_PCT = 0.80
SOFT_WARN_USD = HARD_CAP_USD * SOFT_WARN_PCT


def proposed_risk_from_plan(
    *,
    max_loss: float | None,
    capital_required: float | None,
) -> float:
    if max_loss is not None:
        return abs(float(max_loss))
    if capital_required is not None:
        return abs(float(capital_required))
    return 0.0


def risk_snapshot(
    positions: list[dict[str, Any]],
    *,
    proposed: float = 0.0,
    max_portfolio_risk_usd: float = HARD_CAP_USD,
) -> dict[str, Any]:
    lim = RiskLimits(max_portfolio_risk_usd=max_portfolio_risk_usd)
    book = evaluate_book(positions, lim)
    agg = book["aggregate_open_risk"]
    would_breach = (agg + float(proposed)) > max_portfolio_risk_usd
    return {
        "aggregate_risk": agg,
        "proposed_risk": round(float(proposed), 2),
        "aggregate_after": round(agg + float(proposed), 2),
        "max_portfolio_risk_usd": float(max_portfolio_risk_usd),
        "soft_warn_usd": SOFT_WARN_USD,
        "headroom": book["headroom"],
        "soft_warn": book["soft_warn"],
        "hard_breach": book["hard_breach"],
        "would_breach": would_breach,
        "state": book["status"] if not would_breach else ("would_breach" if proposed else book["status"]),
        "utilization_pct": book["utilization_pct"],
    }


def enforce_cap(
    *,
    list_open: Callable[[], list[dict[str, Any]]],
    close_position: Callable[[str, Optional[float]], dict[str, Any]],
    record_trim_fill: Callable[[dict[str, Any]], None],
    max_portfolio_risk_usd: float = HARD_CAP_USD,
) -> dict[str, Any]:
    """Legacy callback-style trim; prefer enforce_hard_limits(PaperExecutor)."""

    class _Shim:
        def list_open(self):
            return list_open()

        def get_position(self, pid: str):
            for p in list_open():
                if p.get("id") == pid:
                    return p
            return None

        def close_position(self, pid: str, price=None):
            return close_position(pid, price)

        @property
        def portfolio(self):
            # Minimal surface for enforce_hard_limits
            return {"positions": list_open(), "risk_events": []}

        def _save(self):
            return None

    # Use pick_trim via enforce on a thin wrapper is awkward; inline loop:
    from options_seller.risk.limits import pick_trim_targets

    lim = RiskLimits(max_portfolio_risk_usd=max_portfolio_risk_usd)
    trimmed: list[dict[str, Any]] = []
    opens = [p for p in list_open() if p.get("status") == "open"]
    for pid in pick_trim_targets(opens, lim):
        closed = close_position(pid, None)
        event = {
            "type": "risk_trim",
            "strategy": closed.get("strategy"),
            "underlying": closed.get("underlying"),
            "position_id": closed.get("id"),
            "position_risk": position_risk(closed),
            "realized_pnl": closed.get("realized_pnl"),
        }
        record_trim_fill(event)
        trimmed.append(event)
        opens = [p for p in list_open() if p.get("status") == "open"]
    snap = risk_snapshot(opens, max_portfolio_risk_usd=max_portfolio_risk_usd)
    return {"trimmed": trimmed, "n_trimmed": len(trimmed), "snapshot": snap}
